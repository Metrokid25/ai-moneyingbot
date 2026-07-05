import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preview_rag_trading_rule_export.py"
DOC = ROOT / "docs" / "rag_trading_export_preview.md"


def load_script():
    spec = importlib.util.spec_from_file_location("preview_rag_trading_rule_export", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def registry_row(registry_id: str, *, status="registered_needs_final_review", category="pattern") -> dict:
    return {
        "registry_id": registry_id,
        "created_at": "20260612-030405",
        "updated_at": "20260612-030405",
        "source_draft_file": "agent_reports/rag-approved-memory-rule-candidate-draft-20260612-020304.json",
        "source_rule_candidate_id": f"candidate_{registry_id}",
        "candidate_id": f"candidate_{registry_id}",
        "rule_candidate_id": f"candidate_{registry_id}",
        "source_memory_id": f"memory_{registry_id}",
        "rule_candidate_category": category,
        "draft_status": "approved_for_registry",
        "registry_status": status,
        "rule_candidate_summary": f"Reviewer summary for {registry_id}.",
        "source_question": f"What does DB evidence say about {registry_id}?",
        "source_answer": f"DB-grounded answer for {registry_id}.",
        "evidence_strength": "db_grounded",
        "source_refs": [f"article_id:1001:chunk_id:{registry_id}"],
        "used_sources": [{"source_ref": f"article_id:1001:chunk_id:{registry_id}"}],
        "tags": ["rag_research", "db_only"],
        "boundary_notice": "Trading Bot automatic application is prohibited. This is not a rule export.",
        "schema_name": "rag_rule_candidate_draft",
        "schema_version": 1,
    }


def write_registry(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_registered_needs_final_review_is_default_preview_target(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(
        registry_file,
        [
            registry_row("one", status="registered_needs_final_review"),
            registry_row("archived", status="archived"),
        ],
    )

    summary, _json_path, _md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-040506",
    )

    assert summary["preview_count"] == 1
    assert summary["skipped_status_count"] == 1
    assert summary["candidates"][0]["registry_id"] == "one"


def test_status_filter_can_select_archived_candidates(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(
        registry_file,
        [
            registry_row("one", status="registered_needs_final_review"),
            registry_row("archived", status="archived"),
        ],
    )

    summary, _json_path, _md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        status_filter="archived",
        timestamp="20260612-040506",
    )

    assert summary["preview_count"] == 1
    assert summary["candidates"][0]["registry_id"] == "archived"
    assert summary["candidates"][0]["registry_status"] == "archived"


def test_category_filter_and_limit_are_applied(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(
        registry_file,
        [
            registry_row("risk_one", category="risk_control"),
            registry_row("pattern_one", category="pattern"),
            registry_row("pattern_two", category="pattern"),
        ],
    )

    summary, _json_path, _md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        category_filters=["pattern"],
        limit=1,
        timestamp="20260612-040506",
    )

    assert summary["preview_count"] == 1
    assert summary["skipped_category_count"] == 1
    assert summary["candidates"][0]["registry_id"] == "pattern_one"


def test_dry_run_writes_no_preview_reports(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(registry_file, [registry_row("one")])

    summary, json_path, md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        dry_run=True,
        timestamp="20260612-040506",
    )

    assert summary["preview_count"] == 1
    assert json_path is None
    assert md_path is None
    assert not list(tmp_path.glob("rag-trading-rule-export-preview-*.json"))
    assert not list(tmp_path.glob("rag-trading-rule-export-preview-*.md"))


def test_json_and_markdown_reports_include_boundary_language(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(registry_file, [registry_row("one")])

    _summary, json_path, md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-040506",
    )

    json_report = json.loads(json_path.read_text(encoding="utf-8"))
    md_report = md_path.read_text(encoding="utf-8")
    for text in (json.dumps(json_report), md_report):
        assert "DB-only" in text
        assert "Trading Bot automatic application is prohibited" in text
        assert "not a Trading Bot input file" in text
        assert "not a trading signal" in text


def test_candidate_preview_status_and_source_fields_are_preserved(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(registry_file, [registry_row("one", category="risk_control")])

    summary, _json_path, _md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-040506",
    )

    candidate = summary["candidates"][0]
    assert candidate["export_preview_status"] == "preview_needs_human_review"
    assert candidate["registry_id"] == "one"
    assert candidate["source_rule_candidate_id"] == "candidate_one"
    assert candidate["rule_candidate_category"] == "risk_control"
    assert candidate["source_refs"] == ["article_id:1001:chunk_id:one"]
    assert candidate["used_sources"] == [{"source_ref": "article_id:1001:chunk_id:one"}]


def test_preview_candidate_does_not_create_execution_signal_fields(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(registry_file, [registry_row("one")])

    summary, _json_path, _md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-040506",
    )

    candidate = summary["candidates"][0]
    forbidden_keys = {"buy", "sell", "entry", "exit", "order", "position", "final_rule_status"}
    assert not (forbidden_keys & set(candidate))
    assert "final rule" not in json.dumps(candidate).lower()


def test_registry_file_omission_uses_default_registry_file(tmp_path, monkeypatch):
    preview = load_script()
    registry_file = tmp_path / "rag_rule_candidate_registry.jsonl"
    write_registry(registry_file, [registry_row("one")])
    monkeypatch.setattr(preview, "DEFAULT_REGISTRY_FILE", registry_file)

    summary, _json_path, _md_path = preview.preview_export(
        out_dir=tmp_path,
        timestamp="20260612-040506",
    )

    assert summary["registry_file"] == str(registry_file)
    assert summary["preview_count"] == 1


def test_missing_registry_file_cli_returns_non_zero(tmp_path):
    missing = tmp_path / "missing.jsonl"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--registry-file", str(missing), "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "error:" in result.stderr


def test_help_docs_and_reports_include_preview_boundary_language(tmp_path):
    preview = load_script()
    registry_file = tmp_path / "registry.jsonl"
    write_registry(registry_file, [registry_row("one")])
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    _summary, json_path, _md_path = preview.preview_export(
        registry_file=registry_file,
        out_dir=tmp_path,
        timestamp="20260612-040506",
    )

    assert result.returncode == 0
    report_text = json_path.read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8")
    for text in (result.stdout, report_text, doc_text):
        assert "DB-only" in text
        assert "Trading Bot" in text
        assert "preview" in text
        assert "not a trading signal" in text or "Automated trading signals are not generated" in text


def test_no_external_web_naver_archive_write_or_trading_calls_are_added():
    source = SCRIPT.read_text(encoding="utf-8")

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
        assert fragment not in source
