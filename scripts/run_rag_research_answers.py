from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
RETRIEVAL_GLOB = "rag-research-retrieval-*.jsonl"
MIN_OK_SOURCES = 2
MIN_OK_TOP_SCORE = 0.45
MAX_USED_SOURCES = 5
MAX_SYNTHESIS_POINTS = 4
BANNED_ANSWER_PHRASES = (
    "검색 결과 1의 제목은",
    "검색 결과 2의 제목은",
    "검색 결과 3의 제목은",
    "검색 결과 4의 제목은",
    "검색 결과 5의 제목은",
    "해당 근거에서는",
    "논리가 반복된다",
    "라는 근거 흐름으로 정리된다",
    "다른 preview에서는",
    "추가 preview에서는",
    "보조 근거로는",
    "근거를 하나 더 붙이면",
    "상위 근거 안에서 참고할 수 있는 내용은",
    "DB preview에서",
    "질문은",
    "살펴보면",
)
CURRENT_CONTEXT_TERMS = (
    "현재",
    "지금",
    "오늘",
    "어제",
    "내일",
    "이번 주",
    "다음 주",
    "올해",
    "지난 해",
    "내년",
    "내 년",
    "현 환율",
)


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", " ").split())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
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


def validate_retrieval_record(row: dict[str, Any], line_no: int) -> None:
    question_id = normalize_space(row.get("question_id"))
    question = normalize_space(row.get("question"))
    if not question_id:
        raise ValueError(f"retrieval row {line_no} is missing question_id")
    if not question:
        raise ValueError(f"{question_id} is missing question")
    if row.get("db_only") is not True:
        raise ValueError(f"{question_id} is not marked db_only=true")
    if not isinstance(row.get("results"), list):
        raise ValueError(f"{question_id} results must be a list")


def load_retrieval_records(path: Path) -> list[dict[str, Any]]:
    records = read_jsonl(path)
    if not records:
        raise ValueError(f"{path} contains no retrieval records")
    for index, record in enumerate(records, start=1):
        validate_retrieval_record(record, index)
    return records


def find_latest_retrieval_file(reports_dir: Path = DEFAULT_REPORTS_DIR) -> Path:
    candidates = [path for path in reports_dir.glob(RETRIEVAL_GLOB) if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no {RETRIEVAL_GLOB} files found in {reports_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def split_evidence_sentences(text: Any) -> list[str]:
    normalized = normalize_space(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", normalized)
    sentences: list[str] = []
    for part in parts:
        sentence = normalize_space(part).strip(" -")
        if len(sentence) < 12:
            continue
        sentences.append(sentence)
    return sentences


def split_evidence_clauses(text: Any) -> list[str]:
    clauses: list[str] = []
    for sentence in split_evidence_sentences(text):
        if has_current_context_term(sentence):
            continue
        for clause in re.split(r"[,\u3001;]|(?:\s+\ub530\ub77c\uc11c\s+)|(?:\s+\ub2e4\ub9cc\s+)|(?:\s+\uadf8\ub7f0\ub370\s+)", sentence):
            cleaned = polish_clause(normalize_space(clause).strip(" .\u200b"))
            if is_usable_evidence_clause(cleaned):
                clauses.append(cleaned)
    return clauses


def is_usable_evidence_clause(text: str) -> bool:
    if not (12 <= len(text) <= 90):
        return False
    if has_banned_answer_phrase(text):
        return False
    if has_current_context_term(text):
        return False
    if any(marker in text for marker in ("...", "\u2026", "---", "\u2014", "\u2013", '"')):
        return False
    if "?" in text or text.endswith(("\ubb34\uc5c7\uc774\ub2e4", "\uc65c", "\uac00?")):
        return False
    if "\uc774\ub7f0 \ub188" in text:
        return False
    if any(fragment in text for fragment in ("\ubd10\uc57c \ub41c\ub2e4", "\uc810\ube75", "\uc774\ub807\uac8c \uc77d\uace0", "\ub610 \uac04\ub2e4")):
        return False
    if text.endswith(("\uba74", "\ud558\uba74", "\uac00", "\uc740", "\ub294", "\uc73c\ub85c", "\ub85c")):
        return False
    if has_repeated_clause_fragment(text):
        return False
    return True


def has_repeated_clause_fragment(text: str) -> bool:
    compact = normalize_space(text)
    midpoint = len(compact) // 2
    if midpoint < 12:
        return False
    first = compact[:midpoint].strip()
    second = compact[midpoint:].strip()
    return first and second.startswith(first[: min(len(first), 24)])


def has_banned_answer_phrase(text: Any) -> bool:
    normalized = normalize_space(text)
    return any(phrase in normalized for phrase in BANNED_ANSWER_PHRASES)


def polish_clause(text: str) -> str:
    replacements = (
        ("있는데요", "있다"),
        ("했는데요", "했다"),
        ("하는데요", "한다"),
        ("인데요", "이다"),
        ("잖아요", "다"),
        ("입니다", "이다"),
        ("합니다", "한다"),
        ("됩니다", "된다"),
        ("습니다", "다"),
        ("지요", "다"),
        ("죠", "다"),
    )
    polished = text
    for old, new in replacements:
        if polished.endswith(old):
            polished = polished[: -len(old)] + new
            break
    return polished


def has_current_context_term(text: Any) -> bool:
    normalized = normalize_space(text)
    return any(term in normalized for term in CURRENT_CONTEXT_TERMS)


def used_source_from_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": result.get("rank"),
        "article_id": result.get("article_id"),
        "chunk_id": result.get("chunk_id"),
        "title": result.get("title"),
        "source_ref": result.get("source_ref"),
    }


def usable_results(record: dict[str, Any]) -> list[dict[str, Any]]:
    results = [result for result in record.get("results", []) if isinstance(result, dict)]
    return results[:MAX_USED_SOURCES]


def top_score(results: Sequence[dict[str, Any]]) -> float | None:
    scores = []
    for result in results:
        score = result.get("score")
        if isinstance(score, int | float):
            scores.append(float(score))
    return max(scores) if scores else None


def question_terms(record: dict[str, Any]) -> set[str]:
    text = f"{record.get('question', '')} {record.get('topic', '')}"
    terms = set(re.findall(r"[\uac00-\ud7a3A-Za-z0-9]{2,}", text))
    return {term for term in terms if term not in {"\uc5b4\ub5a4", "\uc65c", "\uc5b8\uc81c", "\uc5b4\ub5bb\uac8c", "\ubb34\uc5c7"}}


def relevance_score(text: str, terms: set[str]) -> int:
    return sum(1 for term in terms if term and term in text)


def collect_synthesis_points(record: dict[str, Any], results: Sequence[dict[str, Any]]) -> list[str]:
    terms = question_terms(record)
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for result in results:
        rank = int(result.get("rank") or 999)
        for text in split_evidence_clauses(result.get("text_preview")):
            if not text or has_current_context_term(text):
                continue
            compact = text[:90].rstrip()
            key = compact.casefold()
            if key in seen:
                continue
            seen.add(key)
            score = relevance_score(compact, terms)
            if score == 0 and rank > 2:
                continue
            candidates.append((score, -rank, compact))
    candidates.sort(key=lambda item: (-item[0], -item[1], len(item[2])))
    return [item[2] for item in candidates[:MAX_SYNTHESIS_POINTS]]


def has_direct_question_evidence(record: dict[str, Any], points: Sequence[str]) -> bool:
    terms = question_terms(record)
    if not terms:
        return bool(points)
    joined = " ".join(points)
    return any(term in joined for term in terms)


def collect_caution_points(record: dict[str, Any], results: Sequence[dict[str, Any]]) -> list[str]:
    caution_terms = ("\ub2e4\ub9cc", "\uadf8\ub7f0\ub370", "\uc81c\ud55c", "\ubd80\ub2f4", "\uc704\ud5d8", "\ud558\ub77d", "\uc545\uc7ac", "\ud658\ucc28\uc190")
    points: list[str] = []
    for result in results:
        for clause in split_evidence_clauses(result.get("text_preview")):
            if any(term in clause for term in caution_terms):
                points.append(clause[:90].rstrip())
                break
        if points:
            break
    return points


def unique_caution(points: Sequence[str], cautions: Sequence[str]) -> str | None:
    point_keys = {point.casefold() for point in points}
    for caution in cautions:
        if caution.casefold() not in point_keys:
            return caution
    return None


def render_sentence(text: str) -> str:
    sentence = normalize_space(text).rstrip(" .")
    if not sentence:
        return ""
    return sentence + "."


def render_inline_clause(text: str) -> str:
    return normalize_space(text).rstrip(" .")


def short_evidence_hint(points: Sequence[str]) -> str:
    if not points:
        return "유효한 text_preview가 충분하지 않다는 것"
    hint = render_inline_clause(points[0])
    if len(hint) > 48:
        hint = hint[:48].rstrip()
    return hint


def question_stem(record: dict[str, Any]) -> str:
    question = normalize_space(record.get("question")).rstrip(" ?")
    return question or "질문"


def answer_status_for_record(record: dict[str, Any], results: Sequence[dict[str, Any]]) -> str:
    retrieval_status = normalize_space(record.get("retrieval_status"))
    backend_status = normalize_space(record.get("backend_status"))
    if retrieval_status == "backend_unavailable" or backend_status in {"unavailable", "empty_collection"}:
        return "backend_unavailable"
    if retrieval_status == "no_results" or not results:
        return "no_evidence"
    score = top_score(results)
    if len(results) < MIN_OK_SOURCES or score is None or score < MIN_OK_TOP_SCORE:
        return "weak_evidence"
    return "ok"


def build_answer_text(
    record: dict[str, Any],
    results: Sequence[dict[str, Any]],
    answer_status: str,
) -> str:
    if answer_status == "backend_unavailable":
        return ""
    if answer_status == "no_evidence":
        return ""

    points = collect_synthesis_points(record, results)
    if answer_status == "weak_evidence":
        hint = short_evidence_hint(points)
        return " ".join(
            [
                "검색된 DB preview만으로는 이 질문에 대한 판단 방식이나 환경을 확정하기 어렵다.",
                f"확인 가능한 단서는 {hint} 수준이다.",
                "따라서 이 근거로는 결론보다 추가 근거 수집이 필요하다.",
            ]
        )
    if not points:
        return ""

    first_point = render_inline_clause(points[0])
    if len(points) > 1:
        second_point = render_inline_clause(points[1])
        first_sentence = f"DB 근거상 핵심은 {first_point}이고, {second_point}."
    else:
        first_sentence = f"DB 근거상 핵심은 {first_point}이다."

    sentences = [first_sentence]
    if len(points) > 2:
        third_point = render_inline_clause(points[2])
        sentences.append(f"검색된 근거만 놓고 보면 이 판단은 {third_point}와도 연결된다.")

    caution = unique_caution(points, collect_caution_points(record, results))
    if caution:
        sentences.append(f"단정 범위는 {render_inline_clause(caution)}까지 함께 고려해 제한해야 한다.")
    else:
        sentences.append("세부 조건은 source와 text_preview 범위 안에서만 제한적으로 해석해야 한다.")

    answer = " ".join(sentences)
    if has_banned_answer_phrase(answer):
        raise ValueError("answer synthesis emitted a banned template phrase")
    return answer


def missing_evidence_for_status(answer_status: str, results: Sequence[dict[str, Any]]) -> list[str]:
    if answer_status == "backend_unavailable":
        return ["retrieval backend unavailable"]
    if answer_status == "no_evidence":
        return ["no retrieval results"]
    if answer_status == "weak_evidence":
        score = top_score(results)
        details = []
        if len(results) < MIN_OK_SOURCES:
            details.append(f"retrieved_sources={len(results)}")
        if score is None or score < MIN_OK_TOP_SCORE:
            details.append(f"top_score={score}")
        return ["DB 근거만으로는 부족함" + (f" ({', '.join(details)})" if details else "")]
    return []


def build_answer_record(record: dict[str, Any]) -> dict[str, Any]:
    results = usable_results(record)
    answer_status = answer_status_for_record(record, results)
    synthesis_points = collect_synthesis_points(record, results)
    if answer_status == "ok" and len(synthesis_points) < 2:
        answer_status = "weak_evidence"
    if answer_status == "ok" and not has_direct_question_evidence(record, synthesis_points):
        answer_status = "weak_evidence"
    used_sources = [used_source_from_result(result) for result in results] if answer_status in {"ok", "weak_evidence"} else []
    answer = build_answer_text(record, results, answer_status)
    if answer_status == "weak_evidence" and not answer:
        answer = build_answer_text(record, results, answer_status)
    missing_evidence = missing_evidence_for_status(answer_status, results)
    if answer_status == "weak_evidence" and not synthesis_points:
        missing_evidence.append("no usable text_preview evidence")

    return {
        "question_id": record["question_id"],
        "question": record["question"],
        "topic": record.get("topic"),
        "db_only": record.get("db_only") is True,
        "answer_status": answer_status,
        "answer": answer,
        "used_sources": used_sources,
        "unsupported_claims": [],
        "missing_evidence": missing_evidence,
    }


def build_answer_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_answer_record(record) for record in records]


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def escape_markdown_table(value: Any) -> str:
    return normalize_space(value).replace("|", "\\|")


def format_markdown_report(
    rows: Sequence[dict[str, Any]],
    *,
    retrieval_file: Path,
    generated_at: str,
) -> str:
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("answer_status"))
        status_counts[status] = status_counts.get(status, 0) + 1

    lines = [
        "# RAG DB-only Research Answer Drafts",
        "",
        f"- generated_at: {generated_at}",
        "- db_only: true",
        f"- retrieval_file: {retrieval_file}",
        f"- question_count: {len(rows)}",
    ]
    for status in sorted(status_counts):
        lines.append(f"- answer_{status}: {status_counts[status]}")

    lines.extend(["", "## Questions", ""])
    for row in rows:
        lines.extend(
            [
                f"### {row['question_id']}",
                "",
                f"- status: {row['answer_status']}",
                f"- topic: {row.get('topic')}",
                f"- question: {row['question']}",
                "",
            ]
        )
        if row.get("answer"):
            lines.extend([str(row["answer"]), ""])
        else:
            lines.extend(["답변을 생성하지 않았습니다.", ""])

        used_sources = row.get("used_sources") or []
        if used_sources:
            lines.extend(["| rank | article_id | chunk_id | title | source_ref |", "| --- | --- | --- | --- | --- |"])
            for source in used_sources:
                lines.append(
                    "| {rank} | {article_id} | {chunk_id} | {title} | {source_ref} |".format(
                        rank=source.get("rank"),
                        article_id=source.get("article_id"),
                        chunk_id=source.get("chunk_id"),
                        title=escape_markdown_table(source.get("title")),
                        source_ref=escape_markdown_table(source.get("source_ref")),
                    )
                )
            lines.append("")

        missing = row.get("missing_evidence") or []
        if missing:
            lines.append(f"- missing_evidence: {', '.join(str(item) for item in missing)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate DB-only draft answers from RAG research retrieval reports.",
    )
    parser.add_argument(
        "--retrieval-file",
        type=Path,
        default=None,
        help="Research retrieval JSONL. Defaults to latest agent_reports/rag-research-retrieval-*.jsonl.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def resolve_retrieval_file(path: Path | None) -> Path:
    return path if path is not None else find_latest_retrieval_file()


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        retrieval_file = resolve_retrieval_file(args.retrieval_file)
        retrieval_records = load_retrieval_records(retrieval_file)
        answer_records = build_answer_records(retrieval_records)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stamp = args.timestamp or timestamp_now()
    jsonl_path = args.out_dir / f"rag-research-answers-{stamp}.jsonl"
    md_path = args.out_dir / f"rag-research-answers-{stamp}.md"
    write_jsonl(jsonl_path, answer_records)
    md_path.write_text(
        format_markdown_report(answer_records, retrieval_file=retrieval_file, generated_at=stamp),
        encoding="utf-8-sig",
        newline="\n",
    )

    print(f"Generated {len(answer_records)} DB-only research answer drafts")
    print(f"JSONL: {jsonl_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
