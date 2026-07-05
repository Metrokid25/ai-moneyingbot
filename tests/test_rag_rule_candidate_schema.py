import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DRAFT_SCRIPT = ROOT / "scripts" / "draft_rag_approved_memory_rule_candidates.py"
VALIDATOR_SCRIPT = ROOT / "scripts" / "validate_rag_rule_candidate_drafts.py"
SCHEMA_DOC = ROOT / "docs" / "rag_rule_candidate_schema.md"


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def preview_candidate(memory_id: str, *, category="pattern") -> dict:
    return {
        "memory_id": memory_id,
        "question_id": f"research_{memory_id}",
        "question": f"What does DB evidence say about {memory_id}?",
        "answer": f"DB-backed answer for {memory_id}.",
        "evidence_strength": "db_grounded",
        "source_refs": [f"article_id:1001:chunk_id:{memory_id}"],
        "used_sources": [{"source_ref": f"article_id:1001:chunk_id:{memory_id}"}],
        "tags": ["rag_research", "db_only"],
        "promotion_status": "approved",
        "promotion_review": {"status": "approved", "reviewer": "tester"},
        "suggested_export_category": category,
        "suggested_rule_candidate_summary": f"Reviewer summary for {memory_id}.",
    }


def write_preview(path: Path, candidates: list[dict]) -> None:
    report = {
        "memory_store_file": "agent_reports/rag_research_memory_store.jsonl",
        "generated_at": "20260612-010203",
        "approved_count": len(candidates),
        "dry_run": False,
        "db_only_notice": "DB-only approved memory export preview.",
        "trading_boundary_notice": "Trading Bot automatic application is prohibited.",
        "preview_only_notice": "This file is an export preview, not a rule export.",
        "candidates": candidates,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")


def sample_draft_report(tmp_path: Path, *, category="pattern") -> tuple[dict, Path]:
    draft = load_script(DRAFT_SCRIPT, "draft_rag_approved_memory_rule_candidates")
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(preview_file, [preview_candidate("ragmem_one", category=category)])
    report, json_path, _md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        timestamp="20260612-020304",
    )
    assert json_path is not None
    return report, json_path


def write_draft(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report), encoding="utf-8")


def test_draft_script_sample_json_passes_validator(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    _report, draft_file = sample_draft_report(tmp_path)

    summary, resolved = validator.validate_draft_file(draft_file=draft_file)

    assert resolved == draft_file
    assert summary["valid"] is True
    assert summary["error_count"] == 0
    assert summary["candidate_count"] == 1


def test_missing_top_level_field_fails(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    report, draft_file = sample_draft_report(tmp_path)
    del report["generated_at"]
    write_draft(draft_file, report)

    summary, _resolved = validator.validate_draft_file(draft_file=draft_file)

    assert summary["valid"] is False
    assert any(error["scope"] == "top_level" and error["field"] == "generated_at" for error in summary["errors"])


def test_missing_candidate_field_fails(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    report, draft_file = sample_draft_report(tmp_path)
    del report["candidates"][0]["source_memory_id"]
    write_draft(draft_file, report)

    summary, _resolved = validator.validate_draft_file(draft_file=draft_file)

    assert summary["valid"] is False
    assert any(error["field"] == "source_memory_id" for error in summary["errors"])


def test_invalid_draft_status_fails(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    report, draft_file = sample_draft_report(tmp_path)
    report["candidates"][0]["draft_status"] = "final_rule"
    write_draft(draft_file, report)

    summary, _resolved = validator.validate_draft_file(draft_file=draft_file)

    assert summary["valid"] is False
    assert any(error["field"] == "draft_status" for error in summary["errors"])


def test_invalid_category_fails(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    report, draft_file = sample_draft_report(tmp_path)
    report["candidates"][0]["rule_candidate_category"] = "final_rule"
    write_draft(draft_file, report)

    summary, _resolved = validator.validate_draft_file(draft_file=draft_file)

    assert summary["valid"] is False
    assert any(error["field"] == "rule_candidate_category" for error in summary["errors"])


def test_valid_categories_pass(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    for category in sorted(validator.ALLOWED_CATEGORIES):
        report, draft_file = sample_draft_report(tmp_path / category, category=category)
        summary, _resolved = validator.validate_draft_file(draft_file=draft_file)
        assert report["candidates"][0]["rule_candidate_category"] == category
        assert summary["valid"] is True


def test_validator_format_json_output_includes_summary(tmp_path):
    _report, draft_file = sample_draft_report(tmp_path)

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT), "--draft-file", str(draft_file), "--format", "json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["valid"] is True
    assert summary["candidate_count"] == 1
    assert "errors" in summary


def test_out_file_writes_validation_summary_json(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    _report, draft_file = sample_draft_report(tmp_path)
    out_file = tmp_path / "validation-summary.json"

    summary, _resolved = validator.validate_draft_file(draft_file=draft_file, out_file=out_file)

    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert summary["valid"] is True
    assert saved["valid"] is True
    assert saved["draft_file"] == str(draft_file)


def test_dry_run_does_not_write_validation_summary(tmp_path):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    _report, draft_file = sample_draft_report(tmp_path)
    out_file = tmp_path / "validation-summary.json"

    summary, _resolved = validator.validate_draft_file(draft_file=draft_file, out_file=out_file, dry_run=True)

    assert summary["valid"] is True
    assert not out_file.exists()


def test_draft_file_omission_finds_latest_draft_json(tmp_path, monkeypatch):
    validator = load_script(VALIDATOR_SCRIPT, "validate_rag_rule_candidate_drafts")
    _old_report, old_file = sample_draft_report(tmp_path / "old")
    _new_report, new_file = sample_draft_report(tmp_path / "new")
    older = tmp_path / "rag-approved-memory-rule-candidate-draft-20260612-010203.json"
    newer = tmp_path / "rag-approved-memory-rule-candidate-draft-20260612-040506.json"
    older.write_text(old_file.read_text(encoding="utf-8"), encoding="utf-8")
    newer.write_text(new_file.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(validator, "DEFAULT_REPORTS_DIR", tmp_path)

    summary, resolved = validator.validate_draft_file()

    assert summary["valid"] is True
    assert resolved == newer


def test_boundary_language_is_in_schema_doc_help_and_report(tmp_path):
    _report, draft_file = sample_draft_report(tmp_path)
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    report_text = draft_file.read_text(encoding="utf-8")
    doc_text = SCHEMA_DOC.read_text(encoding="utf-8")

    assert result.returncode == 0
    for text in (result.stdout, report_text, doc_text):
        assert "DB-only" in text
        assert "Trading Bot" in text
        assert "not a final" in text or "not confirmed" in text or "not a rule export" in text


def test_no_external_web_naver_archive_write_or_trading_calls_are_added():
    combined = "\n".join(
        [
            VALIDATOR_SCRIPT.read_text(encoding="utf-8"),
            DRAFT_SCRIPT.read_text(encoding="utf-8"),
        ]
    )

    forbidden_fragments = [
        "requests.",
        "urllib",
        "http://",
        "https://",
        "daily_archive.py",
        "batch_recollect.py",
        "index_tail.py",
        "collector.py",
        "browser.py",
        "parser.py",
        "trading_bot",
        "TradingBot",
        "subprocess.run",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in combined
