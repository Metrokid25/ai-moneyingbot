import importlib.util
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_rulebook_rag_gold.py"
RULES = ROOT / "output" / "pdf" / "굿머닝_매매원칙_검증판_v2_rules.jsonl"
DOC = ROOT / "docs" / "RAG_RULEBOOK_GOLD_EVAL.md"


def load_script():
    spec = importlib.util.spec_from_file_location("build_rulebook_rag_gold", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gold_has_two_questions_for_every_rule():
    module = load_script()
    rows = module.build_gold(RULES)
    summary = module.validate_gold(rows)

    assert summary == {
        "question_count": 24,
        "rule_count": 12,
        "unique_article_count": 24,
        "unique_chunk_count": 24,
    }
    assert Counter(row["question_kind"] for row in rows) == {"core": 12, "caveat": 12}


def test_expected_article_ids_are_derived_from_expected_chunks():
    module = load_script()
    rows = module.build_gold(RULES)

    for row in rows:
        derived = sorted({int(chunk_id.split(":", 1)[0]) for chunk_id in row["expected_chunk_ids"]})
        assert row["expected_article_ids"] == derived
        assert row["expected_keywords"]
        assert row["expected_evidence_roles"]


def test_every_expected_article_is_rulebook_evidence():
    module = load_script()
    rules = {row["rule_id"]: row for row in module.read_jsonl(RULES)}
    rows = module.build_gold(RULES)

    for row in rows:
        source_ids = {source["article_id"] for source in rules[row["rule_id"]]["sources"]}
        assert set(row["expected_article_ids"]) <= source_ids


def test_jsonl_round_trip_and_existing_evaluator_fields(tmp_path):
    module = load_script()
    rows = module.build_gold(RULES)
    out = tmp_path / "gold.jsonl"
    module.write_jsonl(out, rows)
    loaded = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]

    assert loaded == rows
    assert all(row["id"] and row["question"] and row["expected_chunk_ids"] for row in loaded)


def test_docs_separate_retrieval_quality_from_trading_performance():
    doc = DOC.read_text(encoding="utf-8")
    assert "매매 수익성의 정답지가 아니다" in doc
    assert "API 호출 비용" in doc
    assert "다중 근거가 전부 회수됐다고 주장하지 않는다" in doc
