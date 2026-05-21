import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import answer_question_phase2
from rag_answering import (
    build_answer_messages,
    build_answer_record,
    build_sources,
    call_llm,
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
            "title": "금리와 주식시장",
            "text": "금리 인상기에는 할인율 부담과 유동성 축소가 함께 언급된다.",
        }
    ]


def test_prompt_contains_context_and_query():
    context = format_context_for_prompt(sample_context_items())
    messages = build_answer_messages("금리 인상 국면 질문", context)

    rendered = "\n".join(message["content"] for message in messages)

    assert "금리 인상 국면 질문" in rendered
    assert "금리 인상기에는 할인율 부담" in rendered
    assert "chunk_id: 10:0" in rendered


def test_prompt_instructs_no_guessing_without_evidence():
    context = format_context_for_prompt(sample_context_items())
    messages = build_answer_messages("질문", context)

    rendered = "\n".join(message["content"] for message in messages)

    assert "근거 context에 없는 내용은 추측하지 말라" in rendered
    assert "제공된 근거만으로는 확정하기 어렵다" in rendered
    assert "투자 조언처럼 단정하지" in rendered


def test_sources_include_required_fields():
    sources = build_sources(sample_context_items())

    assert sources == [
        {
            "chunk_id": "10:0",
            "article_id": 10,
            "title": "금리와 주식시장",
            "score": 0.91,
        }
    ]


def test_answer_formats_include_sources():
    record = build_answer_record(
        query="질문",
        answer="답변",
        sources=build_sources(sample_context_items()),
        model="gpt-4o-mini",
        top_k=1,
    )

    markdown = format_answer_markdown(record)
    payload = format_answer_json(record)

    assert "## 근거 chunks" in markdown
    assert "chunk_id: 10:0" in markdown
    assert '"sources"' in payload
    assert '"article_id": 10' in payload


@pytest.mark.parametrize("top_k", [1, 5, 20])
def test_top_k_validation_accepts_answer_cli_range(top_k):
    validate_top_k(top_k)


@pytest.mark.parametrize("top_k", [0, 21])
def test_top_k_validation_rejects_out_of_range(top_k):
    with pytest.raises(ValueError, match="--top-k"):
        validate_top_k(top_k)


def test_cli_rejects_dry_run_and_execute_together(capsys):
    result = answer_question_phase2.main(["--query", "질문", "--dry-run", "--execute"])

    captured = capsys.readouterr()

    assert result == 1
    assert "mutually exclusive" in captured.err


def test_cli_without_execute_blocks_before_api_calls(monkeypatch, capsys):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("API or Qdrant should not be called without --execute")

    monkeypatch.setattr(answer_question_phase2, "open_qdrant_client", fail_if_called)
    monkeypatch.setattr(answer_question_phase2, "embed_query", fail_if_called)
    monkeypatch.setattr(answer_question_phase2, "call_llm", fail_if_called)

    result = answer_question_phase2.main(["--query", "질문"])

    captured = capsys.readouterr()

    assert result == 1
    assert "without --execute" in captured.err


def test_llm_call_uses_fake_client_without_api_key():
    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            message = SimpleNamespace(content="근거 기반 답변")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_completions = FakeCompletions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))

    answer = call_llm([{"role": "user", "content": "질문"}], model="fake-model", client=fake_client)

    assert answer == "근거 기반 답변"
    assert fake_completions.kwargs["model"] == "fake-model"
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
