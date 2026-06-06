from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rag_retrieval import (  # noqa: E402
    DEFAULT_COLLECTION,
    DEFAULT_MODEL,
    DEFAULT_QDRANT_PATH,
    DEFAULT_TOP_K,
    embed_query,
    format_search_results,
    get_collection_summary,
    open_qdrant_client,
    search_qdrant,
    validate_top_k,
)


DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
QUESTION_GLOB = "rag-research-questions-*.jsonl"
PREVIEW_CHARS = 220


SearchFn = Callable[..., Any]
EmbedFn = Callable[..., Sequence[float]]


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


def text_preview(value: Any, limit: int = PREVIEW_CHARS) -> str:
    text = normalize_space(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


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


def validate_question_record(row: dict[str, Any], line_no: int) -> None:
    question_id = normalize_space(row.get("question_id"))
    question = normalize_space(row.get("question"))
    if not question_id:
        raise ValueError(f"question row {line_no} is missing question_id")
    if not question:
        raise ValueError(f"{question_id} is missing question")
    if row.get("db_only") is not True:
        raise ValueError(f"{question_id} is not marked db_only=true")
    source_refs = row.get("source_refs")
    if source_refs is not None and not isinstance(source_refs, list):
        raise ValueError(f"{question_id} source_refs must be a list when present")


def load_questions(path: Path) -> list[dict[str, Any]]:
    questions = read_jsonl(path)
    if not questions:
        raise ValueError(f"{path} contains no questions")
    for index, question in enumerate(questions, start=1):
        validate_question_record(question, index)
    return questions


def find_latest_questions_file(reports_dir: Path = DEFAULT_REPORTS_DIR) -> Path:
    candidates = [path for path in reports_dir.glob(QUESTION_GLOB) if path.is_file()]
    if not candidates:
        raise FileNotFoundError(f"no {QUESTION_GLOB} files found in {reports_dir}")
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def source_ref_for_result(row: dict[str, Any]) -> str:
    article_id = row.get("article_id")
    chunk_id = row.get("chunk_id")
    if article_id not in (None, "") and chunk_id not in (None, ""):
        return f"article_id:{article_id}:chunk_id:{chunk_id}"
    if article_id not in (None, ""):
        return f"article_id:{article_id}"
    if chunk_id not in (None, ""):
        return f"chunk_id:{chunk_id}"
    return "unknown"


def structure_result(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "chunk_id": row.get("chunk_id"),
        "article_id": row.get("article_id"),
        "title": row.get("title"),
        "score": row.get("score"),
        "source_ref": source_ref_for_result(row),
        "text_preview": text_preview(row.get("snippet")),
    }


def build_retrieval_record(
    question: dict[str, Any],
    formatted_results: Sequence[dict[str, Any]],
    top_k: int,
    retrieval_error: str | None = None,
) -> dict[str, Any]:
    results = [structure_result(row) for row in formatted_results]
    record = {
        "question_id": question["question_id"],
        "question": question["question"],
        "topic": question.get("topic"),
        "source_refs": list(question.get("source_refs") or []),
        "generated_from": list(question.get("generated_from") or []),
        "db_only": question.get("db_only") is True,
        "top_k": top_k,
        "results": results,
        "retrieval_status": "ok" if results else "no_results",
    }
    if retrieval_error:
        record["retrieval_error"] = retrieval_error
    return record


def build_no_results_records(
    questions: Sequence[dict[str, Any]],
    *,
    top_k: int,
    retrieval_error: str | None = None,
) -> list[dict[str, Any]]:
    validate_top_k(top_k)
    return [
        build_retrieval_record(question, [], top_k, retrieval_error=retrieval_error)
        for question in questions
    ]


def run_retrieval(
    questions: Sequence[dict[str, Any]],
    *,
    client: Any,
    collection: str,
    model: str,
    top_k: int,
    embed_fn: EmbedFn = embed_query,
    search_fn: SearchFn = search_qdrant,
    project_root: Path = PROJECT_ROOT,
) -> list[dict[str, Any]]:
    validate_top_k(top_k)
    records: list[dict[str, Any]] = []
    for question in questions:
        query_vector = embed_fn(question["question"], model=model, project_root=project_root)
        points = search_fn(
            client=client,
            collection=collection,
            query_vector=query_vector,
            top_k=top_k,
        )
        records.append(
            build_retrieval_record(
                question,
                format_search_results(points),
                top_k,
            )
        )
    return records


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def format_markdown_report(
    records: Sequence[dict[str, Any]],
    *,
    questions_file: Path,
    generated_at: str,
    qdrant_path: Path,
    collection: str,
    model: str,
    collection_summary: dict[str, Any],
) -> str:
    ok_count = sum(1 for record in records if record["retrieval_status"] == "ok")
    no_results_count = sum(1 for record in records if record["retrieval_status"] == "no_results")
    lines = [
        "# RAG Research Question Retrieval Report",
        "",
        f"- generated_at: {generated_at}",
        "- db_only: true",
        f"- questions_file: {questions_file}",
        f"- question_count: {len(records)}",
        f"- top_k: {records[0]['top_k'] if records else DEFAULT_TOP_K}",
        f"- retrieval_ok: {ok_count}",
        f"- retrieval_no_results: {no_results_count}",
        f"- qdrant_path: {qdrant_path}",
        f"- collection: {collection}",
        f"- model: {model}",
        "",
        "## Collection",
        "",
    ]
    for key, value in collection_summary.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Questions", ""])
    for record in records:
        lines.extend(
            [
                f"### {record['question_id']}",
                "",
                f"- status: {record['retrieval_status']}",
                f"- topic: {record.get('topic')}",
                f"- question: {record['question']}",
                f"- source_refs: {', '.join(record.get('source_refs') or [])}",
                "",
            ]
        )
        if not record["results"]:
            lines.extend(["No retrieval results.", ""])
            continue
        lines.extend(["| rank | score | article_id | chunk_id | title | preview |", "| --- | --- | --- | --- | --- | --- |"])
        for result in record["results"]:
            lines.append(
                "| {rank} | {score} | {article_id} | {chunk_id} | {title} | {preview} |".format(
                    rank=result.get("rank"),
                    score=result.get("score"),
                    article_id=result.get("article_id"),
                    chunk_id=result.get("chunk_id"),
                    title=escape_markdown_table(result.get("title")),
                    preview=escape_markdown_table(result.get("text_preview")),
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def escape_markdown_table(value: Any) -> str:
    return normalize_space(value).replace("|", "\\|")


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DB-only RAG retrieval for generated research question candidates.",
    )
    parser.add_argument(
        "--questions-file",
        type=Path,
        default=None,
        help="Research question JSONL. Defaults to latest agent_reports/rag-research-questions-*.jsonl.",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--qdrant-path", type=Path, default=PROJECT_ROOT / DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def resolve_questions_file(path: Path | None) -> Path:
    return path if path is not None else find_latest_questions_file()


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        validate_top_k(args.top_k)
        questions_file = resolve_questions_file(args.questions_file)
        questions = load_questions(questions_file)
        client = open_qdrant_client(args.qdrant_path)
        collection_summary = get_collection_summary(client, args.collection)
        if not collection_summary["collection_exists"]:
            records = build_no_results_records(
                questions,
                top_k=args.top_k,
                retrieval_error=f"collection_missing: {args.collection}",
            )
        else:
            records = run_retrieval(
                questions,
                client=client,
                collection=args.collection,
                model=args.model,
                top_k=args.top_k,
            )
    except (OSError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    stamp = args.timestamp or timestamp_now()
    jsonl_path = args.out_dir / f"rag-research-retrieval-{stamp}.jsonl"
    md_path = args.out_dir / f"rag-research-retrieval-{stamp}.md"
    write_jsonl(jsonl_path, records)
    md_path.write_text(
        format_markdown_report(
            records,
            questions_file=questions_file,
            generated_at=stamp,
            qdrant_path=args.qdrant_path,
            collection=args.collection,
            model=args.model,
            collection_summary=collection_summary,
        ),
        encoding="utf-8-sig",
        newline="\n",
    )

    print(f"Retrieved evidence for {len(records)} DB-only research questions")
    if records and all(record.get("retrieval_error") for record in records):
        print(f"Retrieval warning: {records[0]['retrieval_error']}")
    print(f"JSONL: {jsonl_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
