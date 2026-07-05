import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY_SCRIPT = ROOT / "scripts" / "update_rag_rule_candidate_registry.py"
DRAFT_SCRIPT = ROOT / "scripts" / "draft_rag_approved_memory_rule_candidates.py"
VALIDATOR_SCRIPT = ROOT / "scripts" / "validate_rag_rule_candidate_drafts.py"
DOC = ROOT / "docs" / "rag_approved_rule_candidate_registry.md"


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


def sample_draft_file(tmp_path: Path, statuses: list[str | None]) -> tuple[dict, Path]:
    draft = load_script(DRAFT_SCRIPT, "draft_rag_approved_memory_rule_candidates")
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(
        preview_file,
        [preview_candidate(f"ragmem_{index}") for index, _status in enumerate(statuses, start=1)],
    )
    report, json_path, _md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        timestamp="20260612-020304",
    )
    assert json_path is not None
    for candidate, status in zip(report["candidates"], statuses):
        if status is None:
            candidate["draft_status"] = ""
        else:
            candidate["draft_status"] = status
    json_path.write_text(json.dumps(report), encoding="utf-8")
    return report, json_path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_only_approved_for_registry_candidates_are_stored(tmp_path):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    _report, draft_file = sample_draft_file(
        tmp_path,
        ["approved_for_registry", "draft_needs_human_review", "rejected", None, "unknown_status"],
    )
    registry_file = tmp_path / "registry.jsonl"

    summary, json_path, md_path = registry.update_registry(
        draft_file=draft_file,
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-030405",
    )

    rows = read_jsonl(registry_file)
    assert summary["candidate_count"] == 5
    assert summary["approved_for_registry_count"] == 1
    assert summary["added_count"] == 1
    assert summary["skipped_not_approved_count"] == 4
    assert len(rows) == 1
    assert rows[0]["draft_status"] == "approved_for_registry"
    assert rows[0]["registry_status"] == "registered_needs_final_review"
    assert json_path is not None
    assert md_path is not None


def test_duplicate_input_is_idempotent(tmp_path):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    _report, draft_file = sample_draft_file(tmp_path, ["approved_for_registry"])
    registry_file = tmp_path / "registry.jsonl"

    first, _json_path, _md_path = registry.update_registry(
        draft_file=draft_file,
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-030405",
    )
    second, _json_path, _md_path = registry.update_registry(
        draft_file=draft_file,
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-040506",
    )

    assert first["added_count"] == 1
    assert second["added_count"] == 0
    assert second["skipped_duplicate_count"] == 1
    assert len(read_jsonl(registry_file)) == 1


def test_dry_run_writes_no_registry_or_summary_files(tmp_path):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    _report, draft_file = sample_draft_file(tmp_path, ["approved_for_registry"])
    registry_file = tmp_path / "registry.jsonl"

    summary, json_path, md_path = registry.update_registry(
        draft_file=draft_file,
        registry_file=registry_file,
        out_dir=tmp_path,
        dry_run=True,
        timestamp="20260612-030405",
    )

    assert summary["added_count"] == 1
    assert json_path is None
    assert md_path is None
    assert not registry_file.exists()
    assert not list(tmp_path.glob("rag-rule-candidate-registry-update-*.json"))
    assert not list(tmp_path.glob("rag-rule-candidate-registry-update-*.md"))


def test_summary_reports_include_added_and_skipped_counts(tmp_path):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    _report, draft_file = sample_draft_file(tmp_path, ["approved_for_registry", "rejected"])

    summary, json_path, md_path = registry.update_registry(
        draft_file=draft_file,
        registry_file=tmp_path / "registry.jsonl",
        out_dir=tmp_path,
        timestamp="20260612-030405",
    )

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")
    assert summary["added_count"] == 1
    assert saved["skipped_not_approved_count"] == 1
    assert "- added_count: 1" in markdown
    assert "- skipped_not_approved_count: 1" in markdown


def test_registry_record_contains_required_fields_and_no_final_rule_language(tmp_path):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    _report, draft_file = sample_draft_file(tmp_path, ["approved_for_registry"])
    registry_file = tmp_path / "registry.jsonl"

    registry.update_registry(
        draft_file=draft_file,
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-030405",
    )

    record = read_jsonl(registry_file)[0]
    required_fields = {
        "registry_id",
        "created_at",
        "updated_at",
        "source_draft_file",
        "source_rule_candidate_id",
        "candidate_id",
        "rule_candidate_id",
        "source_memory_id",
        "rule_candidate_category",
        "draft_status",
        "registry_status",
        "rule_candidate_summary",
        "source_question",
        "source_answer",
        "evidence_strength",
        "source_refs",
        "used_sources",
        "tags",
        "boundary_notice",
        "schema_name",
        "schema_version",
    }
    assert required_fields <= set(record)
    assert record["registry_status"] == "registered_needs_final_review"
    text = json.dumps(record)
    assert "final approved trading rule" not in text
    assert "live trading" in text
    assert "Trading Bot application" in text


def test_draft_file_omission_finds_latest_draft_json(tmp_path, monkeypatch):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    _old_report, old_file = sample_draft_file(tmp_path / "old", ["approved_for_registry"])
    _new_report, new_file = sample_draft_file(tmp_path / "new", ["approved_for_registry"])
    older = tmp_path / "rag-approved-memory-rule-candidate-draft-20260612-010203.json"
    newer = tmp_path / "rag-approved-memory-rule-candidate-draft-20260612-040506.json"
    older.write_text(old_file.read_text(encoding="utf-8"), encoding="utf-8")
    newer.write_text(new_file.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(registry, "DEFAULT_REPORTS_DIR", tmp_path)

    summary, _json_path, _md_path = registry.update_registry(
        registry_file=tmp_path / "registry.jsonl",
        out_dir=tmp_path,
        timestamp="20260612-030405",
    )

    assert summary["draft_file"] == str(newer)
    assert summary["added_count"] == 1


def test_invalid_draft_schema_fails_registry_update(tmp_path):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    report, draft_file = sample_draft_file(tmp_path, ["approved_for_registry"])
    del report["generated_at"]
    draft_file.write_text(json.dumps(report), encoding="utf-8")

    try:
        registry.update_registry(
            draft_file=draft_file,
            registry_file=tmp_path / "registry.jsonl",
            out_dir=tmp_path,
            timestamp="20260612-030405",
        )
    except ValueError as exc:
        assert "invalid draft schema" in str(exc)
    else:
        raise AssertionError("invalid schema should fail")


def test_boundary_language_is_in_docs_help_and_report(tmp_path):
    registry = load_script(REGISTRY_SCRIPT, "update_rag_rule_candidate_registry")
    _report, draft_file = sample_draft_file(tmp_path, ["approved_for_registry"])
    result = subprocess.run(
        [sys.executable, str(REGISTRY_SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    _summary, json_path, _md_path = registry.update_registry(
        draft_file=draft_file,
        registry_file=tmp_path / "registry.jsonl",
        out_dir=tmp_path,
        timestamp="20260612-030405",
    )

    assert result.returncode == 0
    report_text = json_path.read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8")
    for text in (result.stdout, report_text, doc_text):
        assert "DB-only" in text
        assert "Trading Bot" in text
        assert "not a final" in text or "not a Trading Bot rule" in text or "not approved for live trading" in text


def test_no_external_web_naver_archive_write_or_trading_calls_are_added():
    combined = "\n".join(
        [
            REGISTRY_SCRIPT.read_text(encoding="utf-8"),
            VALIDATOR_SCRIPT.read_text(encoding="utf-8"),
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
