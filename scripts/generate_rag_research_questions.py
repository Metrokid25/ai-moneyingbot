from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, NamedTuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHUNKS_PATH = PROJECT_ROOT / "data" / "chunks_phase2.jsonl"
DEFAULT_EVAL_PATHS = (
    PROJECT_ROOT / "tests" / "fixtures" / "rag_eval_questions.jsonl",
    PROJECT_ROOT / "tests" / "fixtures" / "rag_golden_questions.jsonl",
)
DEFAULT_OUT_DIR = PROJECT_ROOT / "agent_reports"

TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣][A-Za-z0-9가-힣_+./%-]{1,}")
STOPWORDS = {
    "and",
    "are",
    "can",
    "for",
    "from",
    "how",
    "into",
    "the",
    "through",
    "what",
    "when",
    "where",
    "why",
    "with",
    "about",
    "affect",
    "article",
    "chunk",
    "internal",
    "market",
    "markets",
    "question",
    "retrieval",
    "source",
    "stock",
    "stocks",
}


class TopicEvidence(NamedTuple):
    topic: str
    source_ref: str
    generated_from: str
    preview: str


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: row must be a JSON object")
            rows.append(row)
    return rows


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text):
        token = match.group(0).strip("_./%-").casefold()
        if len(token) < 2 or token in STOPWORDS:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def source_ref_from_chunk(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    article_id = chunk.get("article_id") or metadata.get("article_id") or "unknown"
    chunk_id = chunk.get("chunk_id") or metadata.get("chunk_id") or "unknown"
    return f"article_id:{article_id}:chunk_id:{chunk_id}"


def preview_text(text: str, limit: int = 160) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def topic_evidence_from_chunks(chunks: Iterable[dict[str, Any]]) -> list[TopicEvidence]:
    evidence: list[TopicEvidence] = []
    for chunk in chunks:
        metadata = chunk.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        title = normalize_space(metadata.get("title") or chunk.get("title"))
        text = normalize_space(
            chunk.get("embedding_text")
            or chunk.get("text")
            or chunk.get("chunk_text")
            or chunk.get("body_text")
        )
        source_ref = source_ref_from_chunk(chunk)

        for token in dict.fromkeys(tokenize(title)):
            evidence.append(TopicEvidence(token, source_ref, "title", title))
        for token in list(dict.fromkeys(tokenize(text)))[:12]:
            evidence.append(TopicEvidence(token, source_ref, "chunk_keyword", preview_text(text)))
    return evidence


def topic_evidence_from_eval(rows: Iterable[dict[str, Any]], path: Path) -> list[TopicEvidence]:
    evidence: list[TopicEvidence] = []
    for row in rows:
        row_id = normalize_space(row.get("id")) or "unknown"
        source_ref = f"{path.name}:{row_id}"
        question = normalize_space(row.get("question"))
        topics = row.get("expected_topics")
        keywords = row.get("expected_keywords")
        if not isinstance(topics, list):
            topics = []
        if not isinstance(keywords, list):
            keywords = []
        category = normalize_space(row.get("category"))
        terms = [category, *[normalize_space(v) for v in topics], *[normalize_space(v) for v in keywords]]
        for term in terms:
            if term:
                evidence.append(TopicEvidence(term.casefold(), source_ref, "existing_eval", question))

        if question:
            evidence.append(TopicEvidence(question, source_ref, "existing_eval_question", question))
    return evidence


def group_evidence(evidence: Iterable[TopicEvidence]) -> dict[str, list[TopicEvidence]]:
    grouped: dict[str, list[TopicEvidence]] = defaultdict(list)
    for item in evidence:
        topic = normalize_space(item.topic)
        if not topic:
            continue
        refs = {existing.source_ref for existing in grouped[topic]}
        if item.source_ref not in refs:
            grouped[topic].append(item)
    return dict(grouped)


def rank_topics(grouped: dict[str, list[TopicEvidence]]) -> list[tuple[str, list[TopicEvidence]]]:
    source_counts = Counter({topic: len(items) for topic, items in grouped.items()})
    return sorted(
        grouped.items(),
        key=lambda item: (-source_counts[item[0]], item[0]),
    )


def build_question(
    index: int,
    topic: str,
    evidence_items: list[TopicEvidence],
) -> dict[str, Any]:
    generated_from = sorted({item.generated_from for item in evidence_items})
    source_refs = [item.source_ref for item in evidence_items[:5]]
    previews = [item.preview for item in evidence_items if item.preview][:3]

    if "existing_eval_question" in generated_from:
        question = topic
        rendered_topic = "existing_eval_question"
    else:
        rendered_topic = topic
        question = f"What investment context does the internal RAG DB associate with '{topic}'?"

    return {
        "question_id": f"research_q_{index:03d}",
        "question": question,
        "topic": rendered_topic,
        "generated_from": generated_from,
        "source_refs": source_refs,
        "db_only": True,
        "status": "candidate",
        "evidence_previews": previews,
    }


def build_research_questions(
    chunks: list[dict[str, Any]],
    eval_rows_by_path: dict[Path, list[dict[str, Any]]],
    max_questions: int,
) -> list[dict[str, Any]]:
    if max_questions < 1:
        raise ValueError("max_questions must be positive")

    evidence = topic_evidence_from_chunks(chunks)
    for path, rows in eval_rows_by_path.items():
        evidence.extend(topic_evidence_from_eval(rows, path))

    ranked = rank_topics(group_evidence(evidence))
    questions: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for topic, items in ranked:
        candidate = build_question(len(questions) + 1, topic, items)
        normalized_question = candidate["question"].casefold()
        if normalized_question in seen_questions:
            continue
        seen_questions.add(normalized_question)
        questions.append(candidate)
        if len(questions) >= max_questions:
            break
    return questions


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def format_markdown_report(
    questions: list[dict[str, Any]],
    chunks_path: Path | None,
    eval_paths: list[Path],
    generated_at: str,
) -> str:
    lines = [
        "# RAG DB-only Research Question Candidates",
        "",
        f"- generated_at: {generated_at}",
        f"- db_only: true",
        f"- question_count: {len(questions)}",
        f"- chunks_path: {chunks_path if chunks_path is not None else '(not used)'}",
        "- eval_paths:",
    ]
    lines.extend(f"  - {path}" for path in eval_paths)
    lines.extend(["", "## Candidates", ""])
    for question in questions:
        lines.extend(
            [
                f"### {question['question_id']}",
                "",
                f"- question: {question['question']}",
                f"- topic: {question['topic']}",
                f"- generated_from: {', '.join(question['generated_from'])}",
                f"- source_refs: {', '.join(question['source_refs'])}",
                f"- status: {question['status']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate DB-only RAG research question candidates from internal artifacts.",
    )
    parser.add_argument("--chunks-path", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument(
        "--eval-path",
        type=Path,
        action="append",
        dest="eval_paths",
        default=None,
        help="Internal evaluation/golden question JSONL. Can be passed more than once.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-questions", type=int, default=20)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    eval_paths = list(args.eval_paths or DEFAULT_EVAL_PATHS)

    chunks: list[dict[str, Any]] = []
    chunks_path_for_report: Path | None = None
    try:
        if args.chunks_path.exists():
            chunks = read_jsonl(args.chunks_path)
            chunks_path_for_report = args.chunks_path
        eval_rows_by_path = {path: read_jsonl(path) for path in eval_paths if path.exists()}
        questions = build_research_questions(chunks, eval_rows_by_path, args.max_questions)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1

    if not questions:
        print("error: no internal RAG material found for question generation")
        return 1

    stamp = args.timestamp or timestamp_now()
    jsonl_path = args.out_dir / f"rag-research-questions-{stamp}.jsonl"
    md_path = args.out_dir / f"rag-research-questions-{stamp}.md"
    write_jsonl(jsonl_path, questions)
    md_path.write_text(
        format_markdown_report(questions, chunks_path_for_report, eval_paths, stamp),
        encoding="utf-8",
        newline="\n",
    )

    print(f"Generated {len(questions)} DB-only research questions")
    print(f"JSONL: {jsonl_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
