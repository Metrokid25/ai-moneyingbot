import json
import os
from pathlib import Path
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from dotenv import load_dotenv
from rag_answer_context import build_context_items, source_identity_key
from rag_retrieval import embed_query, open_qdrant_client, search_qdrant


DEFAULT_ANSWER_MODEL = "gpt-4o-mini"
PRICING_NOTE_ESTIMATE = "estimated from configured per-token model pricing; cached input is not included"
UNKNOWN_PRICING_NOTE = "pricing not configured for this model"
MISSING_USAGE_NOTE = "usage not returned by provider"
NO_CONTEXT_ANSWER = "No related evidence was found, so this question cannot be answered from the provided RAG context."

OPENAI_PRICING_USD_PER_1M_TOKENS = {
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60,
    }
}


@dataclass(frozen=True)
class LlmUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class EstimatedCost:
    model: str
    input_usd: float | None
    output_usd: float | None
    total_usd: float | None
    pricing_note: str


@dataclass(frozen=True)
class LlmResult:
    answer: str
    usage: LlmUsage | None
    estimated_cost: EstimatedCost


SYSTEM_PROMPT = """You are a Korean RAG answer writer for ai-moneyingbot.
Answer in Korean only.
Use only the provided evidence context.
Do not guess or add facts that are not supported by the context.
If the evidence is insufficient, say "제공된 근거만으로는 확정하기 어렵다".
Do not give definitive investment advice. Frame the answer as an interpretation or summary of mentor posts."""


def build_source(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": item.get("source_id"),
        "source_path": item.get("source_path"),
        "chunk_id": item.get("chunk_id"),
        "article_id": item.get("article_id"),
        "content_hash": item.get("content_hash"),
        "url": item.get("url"),
        "source_url": item.get("source_url"),
        "created_at": item.get("created_at"),
        "collected_at": item.get("collected_at"),
        "posted_at": item.get("posted_at"),
        "source": item.get("source"),
        "title": item.get("title"),
        "score": item.get("score"),
    }


def build_sources(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, str]] = set()
    for item in items:
        source = build_source(item)
        identity = source_identity_key(source)
        if identity is not None and identity in seen_sources:
            continue
        if identity is not None:
            seen_sources.add(identity)
        sources.append(source)
    return sources


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _source_matches_context(source: dict[str, Any], context_item: dict[str, Any]) -> bool:
    identity_keys = ("source_id", "chunk_id", "article_id", "content_hash", "url", "source_url")
    for key in identity_keys:
        source_value = source.get(key)
        context_value = context_item.get(key)
        if source_value is not None and context_value is not None and source_value == context_value:
            return True
    return False


def evaluate_answer_grounding(
    record: dict[str, Any],
    context_items: Sequence[dict[str, Any]],
    claim_terms: Sequence[str] = (),
) -> list[str]:
    errors: list[str] = []
    sources = list(record.get("sources") or [])
    citations = list(record.get("citations") or [])
    context_list = list(context_items)

    if sources and not citations:
        errors.append("answer has sources but no citations")
    if citations and not sources:
        errors.append("answer has citations but no sources")
    if context_list and not sources and not record.get("no_context"):
        errors.append("answer has context evidence but no source citations")

    for label, entries in (("source", sources), ("citation", citations)):
        for entry in entries:
            if not any(_source_matches_context(entry, item) for item in context_list):
                errors.append(
                    f"{label} does not match provided context: "
                    f"chunk_id={entry.get('chunk_id')} source_id={entry.get('source_id')}"
                )

    answer_text = _normalized_text(record.get("answer"))
    evidence_text = _normalized_text(
        " ".join(str(item.get(key) or "") for item in context_list for key in ("title", "text"))
    )
    for term in claim_terms:
        normalized_term = _normalized_text(term)
        if normalized_term and normalized_term in answer_text and normalized_term not in evidence_text:
            errors.append(f"unsupported answer claim term not found in evidence: {term}")

    return errors


def assert_answer_grounded(
    record: dict[str, Any],
    context_items: Sequence[dict[str, Any]],
    claim_terms: Sequence[str] = (),
) -> None:
    errors = evaluate_answer_grounding(record, context_items, claim_terms=claim_terms)
    if errors:
        raise AssertionError("Answer is not grounded in provided context:\n- " + "\n- ".join(errors))


def format_context_for_prompt(items: Sequence[dict[str, Any]]) -> str:
    lines = ["# Evidence Context"]
    for item in items:
        lines.extend(
            [
                "",
                f"## Source {item.get('rank')}",
                f"- source_id: {item.get('source_id')}",
                f"- source_path: {item.get('source_path')}",
                f"- chunk_id: {item.get('chunk_id')}",
                f"- article_id: {item.get('article_id')}",
                f"- content_hash: {item.get('content_hash')}",
                f"- url: {item.get('url')}",
                f"- source_url: {item.get('source_url')}",
                f"- created_at: {item.get('created_at')}",
                f"- collected_at: {item.get('collected_at')}",
                f"- posted_at: {item.get('posted_at')}",
                f"- source: {item.get('source')}",
                f"- title: {item.get('title')}",
                f"- score: {item.get('score')}",
                "",
                str(item.get("text") or ""),
            ]
        )
    return "\n".join(lines).rstrip()


def build_user_prompt(query: str, context: str) -> str:
    if not query.strip():
        raise ValueError("--query must not be empty")
    if not context.strip():
        raise ValueError("context must not be empty")
    return "\n".join(
        [
            "사용자 질문:",
            query,
            "",
            "근거 context:",
            context,
            "",
            "작성 지침:",
            "- 한국어로 답하라.",
            "- 근거 context에 없는 내용은 추측하지 말라.",
            "- 확실하지 않은 내용은 \"제공된 근거만으로는 확정하기 어렵다\"라고 말하라.",
            "- 투자 조언처럼 단정하지 말고, 멘토 글 기반 해석/요약으로 답하라.",
        ]
    )


def build_answer_messages(query: str, context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(query, context)},
    ]


def load_openai_api_key() -> str:
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for --execute")
    return api_key


def _extract_chat_completion_text(response: Any) -> str:
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
    return str(content)


def _get_attr_or_key(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def extract_usage(response: Any) -> LlmUsage | None:
    usage = _get_attr_or_key(response, "usage")
    if usage is None:
        return None

    input_tokens = _get_attr_or_key(usage, "prompt_tokens")
    output_tokens = _get_attr_or_key(usage, "completion_tokens")
    total_tokens = _get_attr_or_key(usage, "total_tokens")

    if input_tokens is None or output_tokens is None or total_tokens is None:
        return None

    return LlmUsage(
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        total_tokens=int(total_tokens),
    )


def estimate_openai_cost(model: str, usage: LlmUsage | None) -> EstimatedCost:
    if usage is None:
        return EstimatedCost(
            model=model,
            input_usd=None,
            output_usd=None,
            total_usd=None,
            pricing_note=MISSING_USAGE_NOTE,
        )

    pricing = OPENAI_PRICING_USD_PER_1M_TOKENS.get(model)
    if pricing is None:
        return EstimatedCost(
            model=model,
            input_usd=None,
            output_usd=None,
            total_usd=None,
            pricing_note=UNKNOWN_PRICING_NOTE,
        )

    input_usd = usage.input_tokens * pricing["input"] / 1_000_000
    output_usd = usage.output_tokens * pricing["output"] / 1_000_000
    return EstimatedCost(
        model=model,
        input_usd=input_usd,
        output_usd=output_usd,
        total_usd=input_usd + output_usd,
        pricing_note=PRICING_NOTE_ESTIMATE,
    )


def format_cost_usd(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.8f}".rstrip("0").rstrip(".")


def format_source_value(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value)
    if not text.strip():
        return "unknown"
    return text


def call_llm(
    messages: Sequence[dict[str, str]],
    model: str = DEFAULT_ANSWER_MODEL,
    client: Any | None = None,
) -> LlmResult:
    if client is None:
        load_openai_api_key()
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is not installed; install it before using --execute") from exc
        client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        messages=list(messages),
        temperature=0.2,
    )
    text = _extract_chat_completion_text(response).strip()
    if not text:
        raise RuntimeError("LLM returned an empty answer")
    usage = extract_usage(response)
    return LlmResult(
        answer=text,
        usage=usage,
        estimated_cost=estimate_openai_cost(model, usage),
    )



def run_rag_answer(
    query: str,
    top_k: int,
    model: str,
    embedding_model: str,
    qdrant_path: str | Path,
    collection: str,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    client = open_qdrant_client(Path(qdrant_path))
    query_vector = embed_query(
        query,
        model=embedding_model,
        project_root=Path(project_root) if project_root is not None else None,
    )
    points = search_qdrant(
        client=client,
        collection=collection,
        query_vector=query_vector,
        top_k=top_k,
    )
    context_items = build_context_items(points)
    if not context_items:
        return build_no_context_answer_record(
            query=query,
            model=model,
            top_k=top_k,
        )

    context = format_context_for_prompt(context_items)
    messages = build_answer_messages(query, context)
    llm_result = call_llm(messages, model=model)
    sources = build_sources(context_items)
    return build_answer_record(
        query=query,
        answer=llm_result.answer,
        sources=sources,
        model=model,
        top_k=top_k,
        usage=llm_result.usage,
        estimated_cost=llm_result.estimated_cost,
    )

def build_answer_record(
    query: str,
    answer: str,
    sources: Sequence[dict[str, Any]],
    model: str,
    top_k: int,
    usage: LlmUsage | None = None,
    estimated_cost: EstimatedCost | None = None,
) -> dict[str, Any]:
    if estimated_cost is None:
        estimated_cost = estimate_openai_cost(model, usage)
    source_list = list(sources)
    return {
        "query": query,
        "answer": answer,
        "sources": source_list,
        "citations": source_list,
        "no_context": not bool(source_list),
        "insufficient_context": not bool(source_list),
        "model": model,
        "top_k": top_k,
        "usage": asdict(usage) if usage is not None else None,
        "estimated_cost": asdict(estimated_cost),
    }


def build_no_context_answer_record(query: str, model: str, top_k: int) -> dict[str, Any]:
    return build_answer_record(
        query=query,
        answer=NO_CONTEXT_ANSWER,
        sources=[],
        model=model,
        top_k=top_k,
        usage=None,
    )


def format_answer_markdown(record: dict[str, Any]) -> str:
    lines = [
        "# Phase 2 RAG Answer",
        "",
        "## 질문",
        str(record["query"]),
        "",
        "## 답변",
        str(record["answer"]),
        "",
        "## 근거 chunks",
    ]
    lines.extend(
        [
            "",
            "## Context status",
            f"- no_context: {bool(record.get('no_context'))}",
            f"- insufficient_context: {bool(record.get('insufficient_context'))}",
        ]
    )
    if not record["sources"]:
        lines.append("- No related evidence.")
    for source in record["sources"]:
        lines.extend(
            [
                "",
                f"- chunk_id: {format_source_value(source.get('chunk_id'))}",
                f"  source_id: {format_source_value(source.get('source_id'))}",
                f"  source_path: {format_source_value(source.get('source_path'))}",
                f"  article_id: {format_source_value(source.get('article_id'))}",
                f"  content_hash: {format_source_value(source.get('content_hash'))}",
                f"  url: {format_source_value(source.get('url'))}",
                f"  source_url: {format_source_value(source.get('source_url'))}",
                f"  created_at: {format_source_value(source.get('created_at'))}",
                f"  collected_at: {format_source_value(source.get('collected_at'))}",
                f"  posted_at: {format_source_value(source.get('posted_at'))}",
                f"  source: {format_source_value(source.get('source'))}",
                f"  title: {format_source_value(source.get('title'))}",
                f"  score: {format_source_value(source.get('score'))}",
            ]
        )
    usage = record.get("usage")
    cost = record.get("estimated_cost") or {}
    lines.extend(
        [
            "",
            "## 사용량/예상 비용",
            f"- model: {cost.get('model', record.get('model'))}",
            f"- input_tokens: {usage.get('input_tokens') if usage else 'unknown'}",
            f"- output_tokens: {usage.get('output_tokens') if usage else 'unknown'}",
            f"- total_tokens: {usage.get('total_tokens') if usage else 'unknown'}",
            f"- estimated_cost_usd: {format_cost_usd(cost.get('total_usd'))}",
            f"- pricing_note: {cost.get('pricing_note', UNKNOWN_PRICING_NOTE)}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def format_answer_json(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"
