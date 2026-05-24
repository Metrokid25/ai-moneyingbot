import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "rag_eval_questions.jsonl"


def load_fixture_rows():
    return [
        json.loads(line)
        for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_fixture_jsonl_loads_as_utf8():
    text = FIXTURE_PATH.read_text(encoding="utf-8")

    assert "금리" in text
    assert "반도체" in text


def test_fixture_rows_have_required_fields():
    required = {
        "id",
        "question",
        "category",
        "expected_topics",
        "expected_keywords",
        "expected_article_ids",
        "expected_chunk_ids",
        "expected_date_range",
        "notes",
    }

    for row in load_fixture_rows():
        assert required <= set(row)


def test_fixture_ids_are_unique():
    ids = [row["id"] for row in load_fixture_rows()]

    assert len(ids) == len(set(ids))


def test_fixture_questions_are_not_empty():
    for row in load_fixture_rows():
        assert row["question"].strip()


def test_fixture_expected_keywords_are_lists():
    for row in load_fixture_rows():
        assert isinstance(row["expected_keywords"], list)
        assert 2 <= len(row["expected_keywords"]) <= 5
