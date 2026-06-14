import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "draft_rag_approved_memory_rule_candidates.py"
DOC = ROOT / "docs" / "rag_approved_memory_rule_candidate_draft.md"


def load_script():
    spec = importlib.util.spec_from_file_location("draft_rag_approved_memory_rule_candidates", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def preview_candidate(memory_id: str, *, category="pattern", tags=None, summary=None) -> dict:
    return {
        "memory_id": memory_id,
        "question_id": f"research_{memory_id}",
        "question": f"What does DB evidence say about {memory_id}?",
        "answer": f"DB-backed answer for {memory_id} with reviewer-facing evidence.",
        "evidence_strength": "db_grounded",
        "source_refs": [f"article_id:1001:chunk_id:{memory_id}"],
        "used_sources": [{"source_ref": f"article_id:1001:chunk_id:{memory_id}"}],
        "tags": tags or ["rag_research", "db_only"],
        "promotion_status": "approved",
        "promotion_review": {"status": "approved", "reviewer": "tester"},
        "suggested_export_category": category,
        "suggested_rule_candidate_summary": summary or f"Reviewer summary for {memory_id}.",
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


def test_preview_candidates_are_drafted_into_internal_reports(tmp_path):
    draft = load_script()
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(preview_file, [preview_candidate("ragmem_one")])

    report, json_path, md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        timestamp="20260612-020304",
    )

    assert report["draft_count"] == 1
    candidate = report["draft_candidates"][0]
    assert candidate["draft_id"] == "rag_rule_candidate_draft_0001"
    assert candidate["draft_status"] == draft.DRAFT_STATUS
    assert candidate["source_memory_id"] == "ragmem_one"
    assert candidate["draft_rule_candidate_summary"] == "Reviewer summary for ragmem_one."
    assert json_path is not None
    assert md_path is not None
    assert json_path.name == "rag-approved-memory-rule-candidate-draft-20260612-020304.json"
    assert md_path.name == "rag-approved-memory-rule-candidate-draft-20260612-020304.md"


def test_limit_zero_returns_no_drafts(tmp_path):
    draft = load_script()
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(preview_file, [preview_candidate("ragmem_one"), preview_candidate("ragmem_two")])

    report, _json_path, _md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        limit=0,
        timestamp="20260612-020304",
    )

    assert report["draft_count"] == 0
    assert report["draft_candidates"] == []


def test_limit_tag_filter_and_category_filter_are_applied(tmp_path):
    draft = load_script()
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(
        preview_file,
        [
            preview_candidate("ragmem_risk", category="risk_control", tags=["risk_control", "db_only"]),
            preview_candidate("ragmem_watch", category="watch_condition", tags=["watch", "db_only"]),
            preview_candidate("ragmem_pattern", category="pattern", tags=["pattern", "db_only"]),
        ],
    )

    report, _json_path, _md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        limit=1,
        tag_filters=["db_only"],
        category_filters=["watch_condition", "pattern"],
        timestamp="20260612-020304",
    )

    assert report["draft_count"] == 1
    assert report["draft_candidates"][0]["source_memory_id"] == "ragmem_watch"
    assert report["draft_candidates"][0]["suggested_export_category"] == "watch_condition"


def test_dry_run_does_not_write_draft_reports(tmp_path):
    draft = load_script()
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(preview_file, [preview_candidate("ragmem_one")])

    report, json_path, md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        dry_run=True,
        timestamp="20260612-020304",
    )

    assert report["draft_count"] == 1
    assert json_path is None
    assert md_path is None
    assert not list(tmp_path.glob("rag-approved-memory-rule-candidate-draft-*.json"))
    assert not list(tmp_path.glob("rag-approved-memory-rule-candidate-draft-*.md"))


def test_latest_preview_file_is_used_when_preview_file_is_omitted(tmp_path, monkeypatch):
    draft = load_script()
    older = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    newer = tmp_path / "rag-approved-memory-export-preview-20260612-040506.json"
    write_preview(older, [preview_candidate("ragmem_old")])
    write_preview(newer, [preview_candidate("ragmem_new")])
    monkeypatch.setattr(draft, "DEFAULT_REPORTS_DIR", tmp_path)

    report, _json_path, _md_path = draft.draft_rule_candidates(
        out_dir=tmp_path,
        timestamp="20260612-020304",
    )

    assert report["preview_file"] == str(newer)
    assert report["draft_candidates"][0]["source_memory_id"] == "ragmem_new"


def test_json_and_markdown_reports_include_boundary_language(tmp_path):
    draft = load_script()
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(preview_file, [preview_candidate("ragmem_one")])

    _report, json_path, md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        timestamp="20260612-020304",
    )

    json_report = json.loads(json_path.read_text(encoding="utf-8"))
    md_report = md_path.read_text(encoding="utf-8")
    for text in (json.dumps(json_report), md_report):
        assert "DB-only" in text
        assert "Trading Bot integration is prohibited" in text
        assert "not a rule export" in text
        assert "not confirmed trading rules" in text


def test_invalid_category_filter_fails(tmp_path):
    draft = load_script()
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(preview_file, [preview_candidate("ragmem_one")])

    try:
        draft.draft_rule_candidates(
            preview_file=preview_file,
            out_dir=tmp_path,
            category_filters=["final_rule"],
            timestamp="20260612-020304",
        )
    except ValueError as exc:
        assert "--category-filter" in str(exc)
    else:
        raise AssertionError("invalid category filter should fail")


def test_help_docs_and_reports_include_draft_boundary_language(tmp_path):
    draft = load_script()
    preview_file = tmp_path / "rag-approved-memory-export-preview-20260612-010203.json"
    write_preview(preview_file, [preview_candidate("ragmem_one")])

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    _report, json_path, _md_path = draft.draft_rule_candidates(
        preview_file=preview_file,
        out_dir=tmp_path,
        timestamp="20260612-020304",
    )

    assert result.returncode == 0
    report_text = json_path.read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8")
    for text in (result.stdout, report_text, doc_text):
        assert "DB-only" in text
        assert "Trading Bot" in text
        assert "Draft" in text or "draft" in text


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
