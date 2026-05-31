import json
from pathlib import Path
from typing import Any, Sequence

from rag_retrieval import extract_source_metadata, payload_value


DEFAULT_CONTEXT_TOP_K = 5
MAX_CONTEXT_TOP_K = 10
DEFAULT_SNIPPET_CHARS = 900
DEFAULT_CONTEXT_TEXT_TOKENS = 1800


def truncate_text(text: str | None, max_chars: int = DEFAULT_SNIPPET_CHARS) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if text is None:
        return ""
    normalized = " ".join(str(text).split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars]


def truncate_text_tokens(text: str | None, max_tokens: int) -> str:
    if max_tokens < 0:
        raise ValueError("max_tokens must be non-negative")
    if text is None or max_tokens == 0:
        return ""
    return " ".join(str(text).split()[:max_tokens])


def validate_context_top_k(top_k: int) -> None:
    if not (1 <= top_k <= MAX_CONTEXT_TOP_K):
        raise ValueError(f"--top-k must be between 1 and {MAX_CONTEXT_TOP_K}")


def build_context_item(point: Any, rank: int, max_chars: int = DEFAULT_SNIPPET_CHARS) -> dict[str, Any]:
    payload = point.payload or {}
    raw_text = payload_value(payload, "text")
    text = truncate_text(raw_text, max_chars=max_chars)
    return {
        "rank": rank,
        "score": getattr(point, "score", None),
        **extract_source_metadata(payload),
        "year": payload_value(payload, "year"),
        "month": payload_value(payload, "month"),
        "text": text,
        "empty_text": not bool(text.strip()),
    }


def build_context_items(
    points: Sequence[Any],
    max_chars: int = DEFAULT_SNIPPET_CHARS,
    max_text_tokens: int | None = None,
) -> list[dict[str, Any]]:
    if max_text_tokens is not None and max_text_tokens < 0:
        raise ValueError("max_text_tokens must be non-negative")

    items: list[dict[str, Any]] = []
    remaining_tokens = max_text_tokens
    for point in points:
        if remaining_tokens == 0:
            break
        item = build_context_item(point, rank=len(items) + 1, max_chars=max_chars)
        if remaining_tokens is not None:
            item["text"] = truncate_text_tokens(item["text"], max_tokens=remaining_tokens)
            item["empty_text"] = not bool(item["text"].strip())
            remaining_tokens -= len(item["text"].split())
        items.append(item)
        if remaining_tokens == 0:
            break
    return items


def build_context_record(question: str, results: Sequence[dict[str, Any]], top_k: int) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("--query must not be empty")
    validate_context_top_k(top_k)
    return {
        "question": question,
        "top_k": top_k,
        "results": list(results),
    }


def format_context_markdown(question: str, results: Sequence[dict[str, Any]], top_k: int) -> str:
    record = build_context_record(question, results, top_k)
    lines = [
        "# RAG Answer Context",
        "",
        f"Question: {record['question']}",
        f"Top K: {record['top_k']}",
        "",
        "## Evidence",
    ]
    for result in record["results"]:
        lines.extend(
            [
                "",
                f"{result.get('rank')}. {result.get('title') or ''}",
                f"- source_id: {result.get('source_id')}",
                f"- source_path: {result.get('source_path')}",
                f"- article_id: {result.get('article_id')}",
                f"- chunk_id: {result.get('chunk_id')}",
                f"- content_hash: {result.get('content_hash')}",
                f"- url: {result.get('url')}",
                f"- source_url: {result.get('source_url')}",
                f"- created_at: {result.get('created_at')}",
                f"- collected_at: {result.get('collected_at')}",
                f"- posted_at: {result.get('posted_at')}",
                f"- source: {result.get('source')}",
                f"- score: {result.get('score')}",
                f"- empty_text: {result.get('empty_text')}",
                "",
                str(result.get("text") or ""),
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def format_context_json(question: str, results: Sequence[dict[str, Any]], top_k: int) -> str:
    record = build_context_record(question, results, top_k)
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"


def validate_output_path(out_path: Path, overwrite: bool) -> None:
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"{out_path} already exists; pass --overwrite to replace it")


def write_text_output(path: Path, content: str, overwrite: bool = False) -> None:
    validate_output_path(path, overwrite=overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
