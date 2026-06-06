from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
RETRIEVAL_GLOB = "rag-research-retrieval-*.jsonl"
MIN_OK_SOURCES = 2
MIN_OK_TOP_SCORE = 0.4
MAX_USED_SOURCES = 5
MAX_EVIDENCE_SENTENCES = 6
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
    return " ".join(str(value or "").split())


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

    sentences = ["검색된 DB 근거만 기준으로 정리한 답변 초안입니다."]
    if answer_status == "weak_evidence":
        sentences.append("다만 검색된 근거의 수나 점수가 충분하지 않아 DB 근거만으로는 부족함으로 표시합니다.")

    evidence_sentences: list[str] = []
    for result in results:
        title = normalize_space(result.get("title"))
        preview = normalize_space(result.get("text_preview"))
        if title and not has_current_context_term(title):
            evidence_sentences.append(f"검색 결과 {result.get('rank')}의 제목은 '{title}'입니다.")
        added_from_preview = 0
        for sentence in split_evidence_sentences(preview):
            if has_current_context_term(sentence):
                continue
            evidence_sentences.append(f"해당 근거에서는 {sentence}")
            added_from_preview += 1
            if added_from_preview >= 2:
                break
            if len(evidence_sentences) >= MAX_EVIDENCE_SENTENCES:
                break
        if len(evidence_sentences) >= MAX_EVIDENCE_SENTENCES:
            break

    if not evidence_sentences:
        return ""

    sentences.extend(evidence_sentences[:MAX_EVIDENCE_SENTENCES])
    sentences.append("따라서 이 답변은 위 검색 결과의 제목과 preview에 드러난 범위 안에서만 해석한 것입니다.")
    return " ".join(sentences)


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
    used_sources = [used_source_from_result(result) for result in results] if answer_status in {"ok", "weak_evidence"} else []
    answer = build_answer_text(record, results, answer_status)
    if answer_status == "weak_evidence" and not answer:
        answer = "DB 근거만으로는 부족함."

    return {
        "question_id": record["question_id"],
        "question": record["question"],
        "topic": record.get("topic"),
        "db_only": record.get("db_only") is True,
        "answer_status": answer_status,
        "answer": answer,
        "used_sources": used_sources,
        "unsupported_claims": [],
        "missing_evidence": missing_evidence_for_status(answer_status, results),
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
