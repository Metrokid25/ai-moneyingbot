import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import answer_question_phase2
from rag_answering import (
    DEFAULT_ANSWER_SOURCE_LIMIT,
    LlmUsage,
    build_answer_messages,
    build_answer_record,
    build_sources,
    call_llm,
    estimate_openai_cost,
    extract_usage,
    format_answer_json,
    format_answer_markdown,
    format_context_for_prompt,
)
from rag_retrieval import validate_top_k


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sample_context_items():
    return [
        {
            "rank": 1,
            "score": 0.91,
            "chunk_id": "10:0",
            "article_id": 10,
            "content_hash": "hash-10",
            "url": "https://example.test/articles/10",
            "source_url": "https://example.test/articles/10",
            "created_at": "2026.05.18.",
            "collected_at": "2026-05-18T09:00:00+09:00",
            "posted_at": "2026.05.18.",
            "source": "sample_archive_export",
            "title": "rate and stocks",
            "text": "Higher rates can pressure discounts and liquidity.",
        }
    ]


def test_prompt_contains_context_and_query():
    context = format_context_for_prompt(sample_context_items())
    messages = build_answer_messages("rate hike question", context)

    rendered = "\n".join(message["content"] for message in messages)

    assert "rate hike question" in rendered
    assert "Higher rates can pressure discounts and liquidity." in rendered
    assert "chunk_id: 10:0" in rendered
    assert "url: https://example.test/articles/10" in rendered
    assert "content_hash: hash-10" in rendered


def test_prompt_instructs_no_guessing_without_evidence():
    context = format_context_for_prompt(sample_context_items())
    messages = build_answer_messages("question", context)

    rendered = "\n".join(message["content"] for message in messages)

    assert "Use only the provided evidence context." in rendered
    assert "Do not guess" in rendered
    assert "Do not give definitive investment advice" in rendered


def test_sources_include_required_fields():
    sources = build_sources(sample_context_items())

    assert sources == [
        {
            "source_id": None,
            "source_path": None,
            "chunk_id": "10:0",
            "article_id": 10,
            "content_hash": "hash-10",
            "url": "https://example.test/articles/10",
            "source_url": "https://example.test/articles/10",
            "created_at": "2026.05.18.",
            "collected_at": "2026-05-18T09:00:00+09:00",
            "posted_at": "2026.05.18.",
            "source": "sample_archive_export",
            "title": "rate and stocks",
            "score": 0.91,
        }
    ]


def test_sources_deduplicate_multiple_chunks_for_same_source_article():
    context_items = [
        {
            "rank": 1,
            "score": 0.95,
            "chunk_id": "1001:0",
            "article_id": 1001,
            "content_hash": "hash-1001",
            "url": "https://example.test/articles/1001",
            "source_url": "https://example.test/articles/1001",
            "title": "Rates",
        },
        {
            "rank": 2,
            "score": 0.93,
            "chunk_id": "1001:1",
            "article_id": 1001,
            "content_hash": "hash-1001",
            "url": "https://example.test/articles/1001",
            "source_url": "https://example.test/articles/1001",
            "title": "Rates",
        },
        {
            "rank": 3,
            "score": 0.91,
            "chunk_id": "1002:0",
            "article_id": 1002,
            "content_hash": "hash-1002",
            "url": "https://example.test/articles/1002",
            "source_url": "https://example.test/articles/1002",
            "title": "FX",
        },
    ]

    sources = build_sources(context_items)

    assert [source["chunk_id"] for source in sources] == ["1001:0", "1002:0"]
    assert [source["article_id"] for source in sources] == [1001, 1002]


def test_answer_record_limits_sources_preserving_order_in_json_and_markdown():
    sources = [
        {
            "chunk_id": f"{article_id}:0",
            "article_id": article_id,
            "content_hash": f"hash-{article_id}",
            "url": f"https://example.test/articles/{article_id}",
            "source_url": f"https://example.test/articles/{article_id}",
            "title": f"source {article_id}",
            "score": 1.0 - article_id / 100,
        }
        for article_id in range(1, DEFAULT_ANSWER_SOURCE_LIMIT + 3)
    ]

    record = build_answer_record(
        query="question",
        answer="answer",
        sources=sources,
        model="gpt-4o-mini",
        top_k=len(sources),
    )
    markdown = format_answer_markdown(record)
    payload = json.loads(format_answer_json(record))

    expected_chunk_ids = [f"{article_id}:0" for article_id in range(1, DEFAULT_ANSWER_SOURCE_LIMIT + 1)]
    omitted_chunk_id = f"{DEFAULT_ANSWER_SOURCE_LIMIT + 1}:0"

    assert [source["chunk_id"] for source in record["sources"]] == expected_chunk_ids
    assert [source["chunk_id"] for source in record["citations"]] == expected_chunk_ids
    assert [source["chunk_id"] for source in payload["sources"]] == expected_chunk_ids
    assert f"chunk_id: {expected_chunk_ids[-1]}" in markdown
    assert omitted_chunk_id not in [source["chunk_id"] for source in record["sources"]]
    assert f"chunk_id: {omitted_chunk_id}" not in markdown


def test_answer_formats_include_sources():
    record = build_answer_record(
        query="question",
        answer="answer",
        sources=build_sources(sample_context_items()),
        model="gpt-4o-mini",
        top_k=1,
    )

    markdown = format_answer_markdown(record)
    payload = json.loads(format_answer_json(record))

    assert "## " in markdown
    assert "chunk_id: 10:0" in markdown
    assert "url: https://example.test/articles/10" in markdown
    assert "source_url: https://example.test/articles/10" in markdown
    assert "created_at: 2026.05.18." in markdown
    assert "collected_at: 2026-05-18T09:00:00+09:00" in markdown
    assert "source: sample_archive_export" in markdown
    assert "title: rate and stocks" in markdown
    assert payload["sources"][0]["article_id"] == 10
    assert payload["sources"][0]["content_hash"] == "hash-10"
    assert payload["sources"][0]["url"] == "https://example.test/articles/10"
    assert payload["sources"][0]["source_url"] == "https://example.test/articles/10"
    assert payload["sources"][0]["created_at"] == "2026.05.18."
    assert payload["sources"][0]["collected_at"] == "2026-05-18T09:00:00+09:00"
    assert payload["sources"][0]["source"] == "sample_archive_export"


def test_usage_and_estimated_cost_are_in_answer_formats():
    usage = LlmUsage(input_tokens=10000, output_tokens=1500, total_tokens=11500)
    record = build_answer_record(
        query="question",
        answer="answer",
        sources=build_sources(sample_context_items()),
        model="gpt-4o-mini",
        top_k=1,
        usage=usage,
        estimated_cost=estimate_openai_cost("gpt-4o-mini", usage),
    )

    markdown = format_answer_markdown(record)
    payload = json.loads(format_answer_json(record))

    assert "## 사용량/예상 비용" in markdown
    assert "input_tokens: 10000" in markdown
    assert "output_tokens: 1500" in markdown
    assert "total_tokens: 11500" in markdown
    assert "estimated_cost_usd: 0.0024" in markdown
    assert payload["usage"] == {
        "input_tokens": 10000,
        "output_tokens": 1500,
        "total_tokens": 11500,
    }
    assert payload["estimated_cost"]["input_usd"] == pytest.approx(0.0015)
    assert payload["estimated_cost"]["output_usd"] == pytest.approx(0.0009)
    assert payload["estimated_cost"]["total_usd"] == pytest.approx(0.0024)


def test_extract_usage_reads_openai_chat_usage_shape():
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=10000,
            completion_tokens=1500,
            total_tokens=11500,
        )
    )

    usage = extract_usage(response)

    assert usage == LlmUsage(input_tokens=10000, output_tokens=1500, total_tokens=11500)


def test_extract_usage_accepts_dict_shape():
    response = {"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}

    usage = extract_usage(response)

    assert usage == LlmUsage(input_tokens=10, output_tokens=2, total_tokens=12)


def test_gpt_4o_mini_cost_estimate_uses_configured_prices():
    cost = estimate_openai_cost(
        "gpt-4o-mini",
        LlmUsage(input_tokens=10000, output_tokens=1500, total_tokens=11500),
    )

    assert cost.input_usd == pytest.approx(0.0015)
    assert cost.output_usd == pytest.approx(0.0009)
    assert cost.total_usd == pytest.approx(0.0024)
    assert "estimated" in cost.pricing_note


def test_unknown_model_cost_is_unknown():
    cost = estimate_openai_cost(
        "unknown-model",
        LlmUsage(input_tokens=10000, output_tokens=1500, total_tokens=11500),
    )

    assert cost.input_usd is None
    assert cost.output_usd is None
    assert cost.total_usd is None
    assert cost.pricing_note == "pricing not configured for this model"


@pytest.mark.parametrize("top_k", [1, 5, 20])
def test_top_k_validation_accepts_answer_cli_range(top_k):
    validate_top_k(top_k)


@pytest.mark.parametrize("top_k", [0, 21])
def test_top_k_validation_rejects_out_of_range(top_k):
    with pytest.raises(ValueError, match="--top-k"):
        validate_top_k(top_k)


def test_cli_rejects_dry_run_and_execute_together(capsys):
    result = answer_question_phase2.main(["--query", "question", "--dry-run", "--execute"])

    captured = capsys.readouterr()

    assert result == 1
    assert "mutually exclusive" in captured.err


def test_cli_without_execute_blocks_before_api_calls(monkeypatch, capsys):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("API or Qdrant should not be called without --execute")

    monkeypatch.setattr(answer_question_phase2, "open_qdrant_client", fail_if_called)
    monkeypatch.setattr(answer_question_phase2, "run_rag_answer", fail_if_called)

    result = answer_question_phase2.main(["--query", "question"])

    captured = capsys.readouterr()

    assert result == 1
    assert "without --execute" in captured.err


def test_llm_call_uses_fake_client_without_api_key():
    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            message = SimpleNamespace(content="evidence-based answer")
            usage = SimpleNamespace(prompt_tokens=10000, completion_tokens=1500, total_tokens=11500)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

    fake_completions = FakeCompletions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))

    result = call_llm([{"role": "user", "content": "question"}], model="gpt-4o-mini", client=fake_client)

    assert result.answer == "evidence-based answer"
    assert result.usage == LlmUsage(input_tokens=10000, output_tokens=1500, total_tokens=11500)
    assert result.estimated_cost.total_usd == pytest.approx(0.0024)
    assert fake_completions.kwargs["model"] == "gpt-4o-mini"
    assert fake_completions.kwargs["temperature"] == 0.2


def test_answer_cli_source_has_no_qdrant_write_operations():
    source = inspect.getsource(answer_question_phase2)

    forbidden = [
        "upsert",
        "delete",
        "recreate_collection",
        "create_collection",
        "upload_points",
    ]
    for token in forbidden:
        assert token not in source


def test_requirements_include_openai_dependency_range():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "openai>=2.0.0,<3.0.0" in requirements.splitlines()


def test_run_rag_answer_symbol_exists():
    import rag_answering

    assert hasattr(rag_answering, "run_rag_answer")
