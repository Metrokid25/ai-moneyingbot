import json
import os
from typing import Any, Sequence

from dotenv import load_dotenv


DEFAULT_ANSWER_MODEL = "gpt-4o-mini"


SYSTEM_PROMPT = """You are a Korean RAG answer writer for ai-moneyingbot.
Answer in Korean only.
Use only the provided evidence context.
Do not guess or add facts that are not supported by the context.
If the evidence is insufficient, say "제공된 근거만으로는 확정하기 어렵다".
Do not give definitive investment advice. Frame the answer as an interpretation or summary of mentor posts."""


def build_source(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": item.get("chunk_id"),
        "article_id": item.get("article_id"),
        "title": item.get("title"),
        "score": item.get("score"),
    }


def build_sources(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_source(item) for item in items]


def format_context_for_prompt(items: Sequence[dict[str, Any]]) -> str:
    lines = ["# Evidence Context"]
    for item in items:
        lines.extend(
            [
                "",
                f"## Source {item.get('rank')}",
                f"- chunk_id: {item.get('chunk_id')}",
                f"- article_id: {item.get('article_id')}",
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


def call_llm(
    messages: Sequence[dict[str, str]],
    model: str = DEFAULT_ANSWER_MODEL,
    client: Any | None = None,
) -> str:
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
    return text


def build_answer_record(
    query: str,
    answer: str,
    sources: Sequence[dict[str, Any]],
    model: str,
    top_k: int,
) -> dict[str, Any]:
    return {
        "query": query,
        "answer": answer,
        "sources": list(sources),
        "model": model,
        "top_k": top_k,
    }


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
    for source in record["sources"]:
        lines.extend(
            [
                "",
                f"- chunk_id: {source.get('chunk_id')}",
                f"  article_id: {source.get('article_id')}",
                f"  title: {source.get('title')}",
                f"  score: {source.get('score')}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def format_answer_json(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"
