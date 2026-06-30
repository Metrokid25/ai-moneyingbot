"""Step A: build a corpus-grounded RAG eval gold set.

For each sampled chunk in the qdrant index, ask gpt-4o-mini to write a Korean
question that the chunk uniquely answers, then emit an eval record whose
expected_chunk_ids / expected_article_ids point back at that chunk. The output
matches the schema consumed by scripts/evaluate_rag_retrieval_set.py, so the
laptop's recall@k / MRR runner can use it directly.

This reads the index read-only and only adds a new fixture file; it never
mutates the corpus.

Reproducibility: candidates are drawn from the FULL collection (paginated, not
just the first scroll page) and ordered by point id (a content-independent UUID
hash), and generation uses temperature=0 with a fixed seed. Re-running against
the same index is therefore largely reproducible — but not byte-guaranteed:
OpenAI only documents temperature=0 as approximately deterministic, and changing
the index (e.g. incremental ingest) changes the sample. The run writes to a
temp file and only promotes it to the final path on success, and exits non-zero
if it cannot reach --count, so a partial/short set is never mistaken for a
complete one.

Consumer note: expected_chunk_ids / expected_article_ids are the ground truth
for an id-based recall@k / MRR runner (the laptop's job). The current
scripts/evaluate_rag_retrieval_set.py scores by keyword overlap only and does
not yet match on these ids.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Windows consoles default to cp949 and choke on Korean / zero-width chars.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

from rag_qdrant import QdrantClient  # noqa: E402

DEFAULT_COLLECTION = "goodmorning_chunks"
DEFAULT_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
DEFAULT_OUT_PATH = PROJECT_ROOT / "tests" / "fixtures" / "rag_eval_questions_corpus.jsonl"
DEFAULT_MODEL = "gpt-4o-mini"
ALLOWED_CATEGORIES = {
    "rates",
    "fx",
    "equities",
    "commodities",
    "policy",
    "crypto",
    "general",
}

SYSTEM_PROMPT = (
    "너는 한국어 금융/투자 카페 글을 기반으로 검색 평가용(gold) 질문을 만드는 도구다. "
    "반드시 지시한 JSON 객체만 출력하고 그 외 설명은 하지 마라."
)

USER_PROMPT_TEMPLATE = """아래 [본문]을 읽고, 이 본문이 '유일한 정답'이 되는 검색 평가용 질문을 1개 만들어라.

이 질문은 검색엔진에 그대로 넣을 자기완결적(self-contained) 질의여야 한다. 아래 규칙을 반드시 지켜라.

[필수 규칙]
1. 본문에만 등장하는 고유한 사실을 1개 이상 질문에 박아 넣어라:
   고유명사(기업명/인물/지명/종목명), 구체적 숫자/비율/금액, 날짜/분기 같은 식별자.
   이 사실 덕분에 코퍼스의 다른 글이 아니라 이 글이 유일한 정답이 되도록 한다.
2. 문서를 가리키는 표현 금지: "본문", "이 글", "위 내용", "언급된", "해당 글에서" 같이
   특정 문서를 지목하는 메타 표현을 쓰지 마라. (검색 질의로 성립하지 않음)
3. 해석/의견 금지: "무엇을 의미하나요", "어떻게 보시나요", "이유는 무엇인가요"처럼
   글쓴이의 주관적 해석을 묻지 마라. 본문에 명시된 구체적 사실을 묻는다.
4. 범용 일반론 금지: 고유 식별자 없이 "금리가 주식에 미치는 영향"처럼 코퍼스의 여러 글이
   똑같이 답이 될 수 있는 막연한 매크로 질문을 만들지 마라.
5. 일반상식 금지: "중앙은행 인플레이션 타겟은 몇 %인가"처럼 본문을 읽지 않아도
   배경지식만으로 답할 수 있는 질문을 만들지 마라. 본문을 봐야만 답할 수 있어야 한다.
6. 본문에서 가장 식별력 높은 고유명사(인물/기업/사건/지표명)를 골라 질문에 반드시 포함하라.
7. 본문을 그대로 베껴 붙이지 말고 자연스러운 한국어 질문 1문장으로 묻는다.

[출력 필드]
- question: 위 규칙을 지킨 한국어 질문 1개.
- expected_keywords: 본문에 실제로 등장하는 핵심 단어 3~5개 (한국어, 짧게).
- expected_topics: 한 단계 더 일반적인 주제어 2~3개.
- category: 다음 중 하나만 — rates, fx, equities, commodities, policy, crypto, general.

반드시 이 JSON 스키마로만 출력:
{{"question": "...", "expected_keywords": ["..."], "expected_topics": ["..."], "category": "..."}}

[제목]
{title}

[본문]
{body}
"""


def open_qdrant(qdrant_path: Path) -> QdrantClient:
    if QdrantClient is None:
        raise SystemExit(
            "qdrant_client is not installed in this environment; install it before running Step A."
        )
    try:
        return QdrantClient(path=str(qdrant_path))
    except Exception as exc:  # noqa: BLE001 - surface a clear, actionable message
        raise SystemExit(
            f"failed to open qdrant at {qdrant_path}: {exc}\n"
            "Local qdrant allows a single holder per path. If the RAG web server is "
            "answering a query against this index, stop it (or wait) and retry."
        ) from exc


def iter_candidate_chunks(
    client: QdrantClient,
    collection: str,
    *,
    min_chars: int,
    scan_limit: int,
    dedup_articles: bool,
) -> list[dict[str, Any]]:
    """Scroll the WHOLE collection and keep substantive, article-deduped chunks.

    Pages through every point (scroll returns at most one page per call) instead
    of sampling only the first page, so the candidate pool covers the full
    corpus, not the lowest-UUID prefix. Points are then ordered by point id (a
    content-independent UUIDv5 hash of chunk_id), giving a stable, content-
    independent ordering across runs of the same index. `scan_limit` is a safety
    cap on points scanned (0 = no cap / scan all).
    """
    points: list[Any] = []
    offset: Any = None
    page_size = 1000
    while True:
        page, offset = client.scroll(
            collection,
            limit=page_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(page)
        if offset is None or (scan_limit and len(points) >= scan_limit):
            break
    points = sorted(points, key=lambda p: str(p.id))
    seen_articles: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for point in points:
        payload = point.payload or {}
        text = str(payload.get("text") or "")
        title = str(payload.get("title") or "")
        chunk_id = str(payload.get("chunk_id") or "")
        article_id = str(payload.get("article_id") or "")
        if len(text.strip()) < min_chars:
            continue
        if not chunk_id or not article_id.isdigit():
            continue
        if dedup_articles and article_id in seen_articles:
            continue
        seen_articles.add(article_id)
        candidates.append(
            {
                "chunk_id": chunk_id,
                "article_id": int(article_id),
                "title": title,
                "text": text,
                "url": str(payload.get("url") or payload.get("source_url") or ""),
            }
        )
    return candidates


def generate_question(
    client: Any, model: str, chunk: dict[str, Any], *, attempts: int = 3
) -> tuple[dict[str, Any], Any]:
    """Call the LLM with bounded retry; returns (parsed_json, usage)."""
    body = chunk["text"]
    if len(body) > 2400:
        body = body[:2400]
    prompt = USER_PROMPT_TEMPLATE.format(title=chunk["title"] or "(제목 없음)", body=body)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                seed=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            return data, getattr(response, "usage", None)
        except Exception as exc:  # noqa: BLE001 - retry transient API/parse errors
            last_exc = exc
            if attempt < attempts:
                time.sleep(2 * attempt)
    assert last_exc is not None
    raise last_exc


def _question_tokens(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text))


def is_near_duplicate(question: str, accepted: list[str], *, threshold: float = 0.6) -> bool:
    """True if `question` overlaps an already-accepted question too heavily.

    Two chunks can yield the same factual question (e.g. both about China's
    annual car sales); keeping both would let one retrieved chunk satisfy two
    gold answers and distort recall. Token-overlap vs the shorter question.
    """
    tokens = _question_tokens(question)
    if not tokens:
        return False
    for other in accepted:
        other_tokens = _question_tokens(other)
        if not other_tokens:
            continue
        if len(tokens & other_tokens) / min(len(tokens), len(other_tokens)) >= threshold:
            return True
    return False


def to_str_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


# Phrases that mean the question points at "the passage" instead of being a
# standalone retrieval query — these leak the answer and are never valid.
BANNED_QUESTION_SUBSTRINGS = ("본문", "이 글", "위 내용", "위 글", "해당 글", "이 기사", "윗글")


def build_record(index: int, chunk: dict[str, Any], generated: Any) -> dict[str, Any]:
    if not isinstance(generated, dict):
        # Defensive: response_format=json_object normally yields an object, but a
        # stray array/scalar would otherwise raise AttributeError and abort the run.
        raise ValueError(f"chunk {chunk['chunk_id']}: model output was not a JSON object")
    question = str(generated.get("question") or "").strip()
    if not question:
        raise ValueError(f"chunk {chunk['chunk_id']}: model returned empty question")
    for banned in BANNED_QUESTION_SUBSTRINGS:
        if banned in question:
            raise ValueError(
                f"chunk {chunk['chunk_id']}: question references the source document ({banned!r})"
            )
    category = str(generated.get("category") or "general").strip().lower()
    if category not in ALLOWED_CATEGORIES:
        category = "general"
    keywords = to_str_list(generated.get("expected_keywords"), limit=6) or ["근거"]
    topics = to_str_list(generated.get("expected_topics"), limit=4) or [category]
    return {
        "id": f"corpus-{index:03d}",
        "question": question,
        "category": category,
        "expected_topics": topics,
        "expected_keywords": keywords,
        "expected_article_ids": [chunk["article_id"]],
        "expected_chunk_ids": [chunk["chunk_id"]],
        "expected_date_range": {"start": None, "end": None},
        "notes": f"Auto-generated from chunk {chunk['chunk_id']} (article {chunk['article_id']}).",
        "source_title": chunk["title"],
        "source_url": chunk["url"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=40, help="Number of gold questions to generate.")
    parser.add_argument("--min-chars", type=int, default=400, help="Skip chunks shorter than this.")
    parser.add_argument("--scan-limit", type=int, default=0,
                        help="Safety cap on points scanned (0 = scan the whole collection).")
    parser.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--no-dedup-articles", action="store_true", help="Allow multiple chunks per article.")
    parser.add_argument("--dry-run", action="store_true", help="Sample + preview chunks, no API calls, no write.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    client = open_qdrant(args.qdrant_path)
    candidates = iter_candidate_chunks(
        client,
        args.collection,
        min_chars=args.min_chars,
        scan_limit=args.scan_limit,
        dedup_articles=not args.no_dedup_articles,
    )
    print(f"qualifying chunks: {len(candidates)} | target: {args.count}")
    if len(candidates) < args.count:
        print(f"error: only {len(candidates)} chunks met the bar (need {args.count}); "
              "lower --min-chars or disable --no-dedup-articles.")
        return 1

    if args.dry_run:
        for i, chunk in enumerate(candidates[: args.count], 1):
            preview = chunk["text"].strip().replace("\n", " ")[:90]
            print(f"[{i:02d}] {chunk['chunk_id']}  {chunk['title'][:30]!r}  | {preview}")
        return 0

    from openai import OpenAI

    openai_client = OpenAI()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Write to a sibling temp file and only promote it to args.out on success, so
    # an interrupted/short run never leaves a partial file masquerading as a
    # complete fixture (and never clobbers a previously-good one). The temp file
    # is still written incrementally so a crash leaves recoverable progress.
    partial_path = args.out.with_name(args.out.name + ".partial")
    records: list[dict[str, Any]] = []
    total_in = total_out = 0
    skipped = 0
    with partial_path.open("w", encoding="utf-8") as handle:
        for chunk in candidates:
            if len(records) >= args.count:
                break
            try:
                generated, usage = generate_question(openai_client, args.model, chunk)
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                print(f"  skip {chunk['chunk_id']}: API/parse error: {exc}")
                continue
            # Count tokens for every completed API call, even if the result is
            # then rejected below, so the cost report is not under-stated.
            if usage is not None:
                total_in += getattr(usage, "prompt_tokens", 0) or 0
                total_out += getattr(usage, "completion_tokens", 0) or 0
            try:
                record = build_record(len(records) + 1, chunk, generated)
            except ValueError as exc:
                skipped += 1
                print(f"  skip {chunk['chunk_id']}: {exc}")
                continue
            if is_near_duplicate(record["question"], [r["question"] for r in records]):
                skipped += 1
                print(f"  skip {chunk['chunk_id']}: near-duplicate question")
                continue
            records.append(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{len(records):02d}] {chunk['chunk_id']}  Q: {record['question'][:60]}")

    # gpt-4o-mini pricing: $0.15 / 1M input, $0.60 / 1M output
    est_cost = total_in / 1_000_000 * 0.15 + total_out / 1_000_000 * 0.60
    print(f"tokens in={total_in} out={total_out} | est_cost=${est_cost:.4f}")
    if len(records) < args.count:
        print(f"error: produced {len(records)}/{args.count}; candidate pool exhausted. "
              f"Partial output left at {partial_path} (final file not written).")
        return 1
    partial_path.replace(args.out)
    print(f"wrote {len(records)} records -> {args.out} (skipped {skipped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
