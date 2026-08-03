import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_trading_research_contract.py"
RULES = ROOT / "output" / "pdf" / "굿머닝_매매원칙_검증판_v2_rules.jsonl"
DOC = ROOT / "docs" / "TRADING_RESEARCH_HANDOFF_A_GRADE.md"


def load_script():
    spec = importlib.util.spec_from_file_location("build_trading_research_contract", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_contract_contains_only_a_grade_target_rules_and_real_evidence():
    module = load_script()
    rows = module.build_contracts(RULES)
    summary = module.validate_contracts(rows)

    assert [row["rule_id"] for row in rows] == ["GM-R01", "GM-R03", "GM-R06", "GM-R07"]
    assert summary == {"contract_count": 4, "unique_article_count": 11}
    assert all(row["source_rulebook"]["automation_grade"] == "A" for row in rows)
    assert all(row["source_rulebook"]["rule_status"] == "research_hypothesis_unvalidated" for row in rows)
    assert all(source["article_id"] > 0 for row in rows for source in row["evidence"])
    assert all(source["quote"].strip() for row in rows for source in row["evidence"])


def test_contract_holds_ownership_and_no_auto_apply_boundary():
    module = load_script()
    rows = module.build_contracts(RULES)

    for row in rows:
        boundary = row["ownership_boundary"]
        assert boundary["cross_key"] == "article_id"
        assert boundary["transport"] == "JSONL"
        assert boundary["automatic_application"] is False
        assert boundary["live_trading_authorized"] is False
        assert "must not read or write" in boundary["trading_access"]
        assert row["contract_status"] == "research_only_needs_trading_bot_validation"


def test_protocol_requires_holdout_costs_integrity_and_reproduction():
    module = load_script()
    rows = module.build_contracts(RULES)

    for row in rows:
        protocol_text = json.dumps(row["common_protocol"], ensure_ascii=False)
        schema = row["result_return_contract"]
        assert "sealed holdout" in protocol_text
        assert "stress-cost" in protocol_text
        assert "point-in-time" in protocol_text
        assert "reproduction_command" in schema["required_fields"]
        assert "not_evaluable" in schema["decision_enum"]
        assert "invalid_experiment" in schema["decision_enum"]
        assert "production_signal" in schema["forbidden_fields"]


def test_rule_specific_experiments_have_baseline_grid_objective_and_checks():
    module = load_script()
    rows = module.build_contracts(RULES)

    for row in rows:
        experiment = row["experiment"]
        assert experiment["baseline"]
        assert experiment["candidate_grid"]
        assert experiment["primary_objective"]
        assert experiment["guardrails"]
        assert experiment["special_checks"]


def test_jsonl_round_trip_and_documented_boundary(tmp_path):
    module = load_script()
    rows = module.build_contracts(RULES)
    out = tmp_path / "contract.jsonl"
    module.write_jsonl(out, rows)

    loaded = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows

    doc = DOC.read_text(encoding="utf-8")
    assert "실거래 적용·자동 주문·Trading Bot 규칙 변경을" in doc
    assert "허용 결정값" in doc
    assert "오너의 별도 승인 없이 Trading Bot 코드" in doc
