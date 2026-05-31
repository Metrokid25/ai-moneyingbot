import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import rag_answering
from rag_answering import (
    NO_CONTEXT_ANSWER,
    build_no_context_answer_record,
    format_answer_json,
    format_answer_markdown,
)


def test_no_context_answer_record_has_empty_sources_and_status():
    record = build_no_context_answer_record(
        query="What should I conclude about the market?",
        model="fake-model",
        top_k=3,
    )

    markdown = format_answer_markdown(record)
    payload = json.loads(format_answer_json(record))

    assert payload["answer"] == NO_CONTEXT_ANSWER
    assert payload["sources"] == []
    assert payload["citations"] == []
    assert payload["no_context"] is True
    assert payload["insufficient_context"] is True
    answer_lower = payload["answer"].lower()
    assert "rag corpus" in answer_lower
    assert "does not contain enough related evidence" in answer_lower
    assert "cannot answer from the provided rag context" in answer_lower
    assert "without inventing unsupported facts" in answer_lower
    assert "no_context: True" in markdown
    assert "insufficient_context: True" in markdown
    assert "- No related evidence." in markdown
    assert "will rise" not in answer_lower
    assert "will fall" not in answer_lower
    assert "buy" not in answer_lower
    assert "sell" not in answer_lower


def test_run_rag_answer_short_circuits_empty_retrieval_without_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(rag_answering, "open_qdrant_client", lambda path: object())
    monkeypatch.setattr(rag_answering, "embed_query", lambda *args, **kwargs: [0.0] * 1024)
    monkeypatch.setattr(rag_answering, "search_qdrant", lambda *args, **kwargs: [])

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM must not be called when retrieval returns no evidence")

    monkeypatch.setattr(rag_answering, "call_llm", fail_if_called)

    record = rag_answering.run_rag_answer(
        query="What does the evidence say?",
        top_k=2,
        model="fake-model",
        embedding_model="fake-embedding-model",
        qdrant_path=tmp_path / "qdrant",
        collection="fake_collection",
        project_root=tmp_path,
    )

    assert record["answer"] == NO_CONTEXT_ANSWER
    assert record["sources"] == []
    assert record["citations"] == []
    assert record["no_context"] is True
    assert record["insufficient_context"] is True
