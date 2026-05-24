import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import evaluate_rag_retrieval_set as eval_set


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def question_row(**overrides):
    row = {
        "id": "eval-001",
        "question": "금리 인상이 주식시장에 어떤 영향을 주나요?",
        "category": "rates",
        "expected_topics": ["금리", "주식시장"],
        "expected_keywords": ["금리", "주식", "유동성"],
        "expected_article_ids": [],
        "expected_chunk_ids": [],
        "expected_date_range": {"start": None, "end": None},
        "notes": "sample",
    }
    row.update(overrides)
    return row


def test_load_questions_accepts_valid_jsonl(tmp_path):
    path = write_jsonl(tmp_path / "questions.jsonl", [question_row()])

    questions = eval_set.load_questions(path)

    assert questions[0]["id"] == "eval-001"


def test_load_questions_rejects_invalid_jsonl(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")

    with pytest.raises(eval_set.EvaluationInputError, match="invalid JSON"):
        eval_set.load_questions(path)


def test_load_questions_rejects_duplicate_ids(tmp_path):
    path = write_jsonl(tmp_path / "questions.jsonl", [question_row(), question_row()])

    with pytest.raises(eval_set.EvaluationInputError, match="duplicate id"):
        eval_set.load_questions(path)


def test_score_question_counts_keyword_hits():
    score = eval_set.score_question(
        question_row(),
        [
            {
                "rank": 1,
                "score": 0.61,
                "chunk_id": "123:0",
                "article_id": 123,
                "title": "금리와 주식시장",
                "posted_at": "2024.01.01.",
                "snippet": "유동성이 줄어들면 주식이 부담을 받을 수 있다.",
            }
        ],
    )

    assert score["keyword_hit_count"] == 3
    assert score["matched_keywords"] == ["금리", "주식", "유동성"]


def test_score_question_calculates_keyword_hit_rate_and_pass():
    score = eval_set.score_question(
        question_row(expected_keywords=["금리", "환율", "부동산"]),
        [{"title": "금리 이야기", "snippet": "주식시장과 금리"}],
    )

    assert score["keyword_hit_rate"] == pytest.approx(1 / 3)
    assert score["pass"] is True


def test_score_question_skips_pass_when_no_keywords():
    score = eval_set.score_question(question_row(expected_keywords=[]), [{"title": "anything"}])

    assert score["keyword_hit_rate"] is None
    assert score["pass"] is None


def test_load_mock_results_and_evaluate(tmp_path):
    questions = [question_row()]
    path = write_jsonl(
        tmp_path / "mock.jsonl",
        [
            {
                "id": "eval-001",
                "results": [
                    {
                        "rank": 1,
                        "score": 0.5,
                        "chunk_id": "1:0",
                        "article_id": 1,
                        "title": "금리",
                        "snippet": "주식과 유동성",
                    }
                ],
            }
        ],
    )

    mock_results = eval_set.load_mock_results(path)
    scores = eval_set.evaluate_mock_results(questions, mock_results)

    assert scores[0]["retrieved_count"] == 1
    assert scores[0]["top_score"] == 0.5
    assert scores[0]["keyword_hit_rate"] == pytest.approx(1.0)


def test_execute_returns_not_implemented_without_api_calls(capsys):
    result = eval_set.main(["--execute"])

    captured = capsys.readouterr()
    assert result == 2
    assert "not implemented" in captured.err


def test_default_dry_run_does_not_require_mock_results(capsys):
    result = eval_set.main(["--dry-run"])

    captured = capsys.readouterr()
    assert result == 0
    assert "api_calls: false" in captured.out
    assert "qdrant_search: false" in captured.out
