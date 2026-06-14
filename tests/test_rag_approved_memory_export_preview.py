import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "preview_rag_approved_memory_export.py"
DOC = ROOT / "docs" / "rag_approved_memory_export_preview.md"


def load_script():
    spec = importlib.util.spec_from_file_location("preview_rag_approved_memory_export", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def memory(memory_id: str, status=None, *, review_status=None, tags=None, answer=None) -> dict:
    row = {
        "memory_id": memory_id,
        "question_id": f"research_{memory_id}",
        "question": f"What does DB evidence say about {memory_id}?",
        "answer": answer or f"DB-backed answer for {memory_id} with a repeatable pattern.",
        "evidence_strength": "db_grounded",
        "source_refs": [f"article_id:1001:chunk_id:{memory_id}"],
        "used_sources": [{"source_ref": f"article_id:1001:chunk_id:{memory_id}"}],
        "tags": tags or ["rag_research", "db_only"],
    }
    if status is not None:
        row["promotion_status"] = status
    if review_status is not None:
        row["promotion_review"] = {
            "status": review_status,
            "note": "reviewed by human",
            "reviewer": "tester",
            "reviewed_at": "20260612-010203",
        }
    return row


def test_promotion_status_approved_records_are_preview_candidates(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_approved", "approved")])

    summary, _json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    assert summary["approved_count"] == 1
    assert summary["candidates"][0]["memory_id"] == "ragmem_approved"


def test_promotion_review_status_approved_records_are_preview_candidates(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_review_approved", "pending", review_status="approved")])

    summary, _json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    assert summary["approved_count"] == 1
    assert summary["candidates"][0]["memory_id"] == "ragmem_review_approved"
    assert summary["candidates"][0]["promotion_review"]["status"] == "approved"


def test_pending_rejected_and_empty_status_are_excluded_by_default(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(
        store,
        [
            memory("ragmem_pending", "pending"),
            memory("ragmem_rejected", "rejected"),
            memory("ragmem_empty", ""),
            memory("ragmem_missing"),
        ],
    )

    summary, _json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    assert summary["approved_count"] == 0
    assert summary["candidates"] == []


def test_limit_is_applied(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_one", "approved"), memory("ragmem_two", "approved")])

    summary, _json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        limit=1,
        timestamp="20260612-010203",
    )

    assert summary["approved_count"] == 1
    assert summary["candidates"][0]["memory_id"] == "ragmem_one"


def test_limit_zero_returns_no_candidates(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_one", "approved"), memory("ragmem_two", "approved")])

    summary, _json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        limit=0,
        timestamp="20260612-010203",
    )

    assert summary["approved_count"] == 0
    assert summary["candidates"] == []


def test_tag_filter_is_applied(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(
        store,
        [
            memory("ragmem_risk", "approved", tags=["risk_control", "db_only"]),
            memory("ragmem_pattern", "approved", tags=["pattern", "db_only"]),
        ],
    )

    summary, _json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        tag_filters=["risk_control"],
        timestamp="20260612-010203",
    )

    assert summary["approved_count"] == 1
    assert summary["candidates"][0]["memory_id"] == "ragmem_risk"


def test_dry_run_does_not_write_preview_reports(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_approved", "approved")])

    summary, json_path, md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        dry_run=True,
        timestamp="20260612-010203",
    )

    assert summary["approved_count"] == 1
    assert json_path is None
    assert md_path is None
    assert not list(tmp_path.glob("rag-approved-memory-export-preview-*.json"))
    assert not list(tmp_path.glob("rag-approved-memory-export-preview-*.md"))


def test_json_and_markdown_reports_include_required_boundary_language(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_approved", "approved")])

    _summary, json_path, md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    assert json_path is not None
    assert md_path is not None
    json_report = json.loads(json_path.read_text(encoding="utf-8"))
    md_report = md_path.read_text(encoding="utf-8")
    for text in (json.dumps(json_report), md_report):
        assert "DB-only" in text
        assert "Trading Bot automatic application is prohibited" in text
        assert "export preview, not a rule export" in text


def test_suggested_category_is_allowed_and_summary_is_generated(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(
        store,
        [
            memory(
                "ragmem_risk",
                "approved",
                answer="DB memory says avoid oversizing when drawdown risk rises.",
            )
        ],
    )

    summary, _json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    candidate = summary["candidates"][0]
    assert candidate["suggested_export_category"] in preview.ALLOWED_EXPORT_CATEGORIES
    assert candidate["suggested_rule_candidate_summary"]
    assert "drawdown risk" in candidate["suggested_rule_candidate_summary"]


def test_help_docs_and_reports_include_preview_boundary_language(tmp_path):
    preview = load_script()
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_approved", "approved")])

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    _summary, json_path, _md_path = preview.preview_export(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    assert result.returncode == 0
    report_text = json_path.read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8")
    for text in (result.stdout, report_text, doc_text):
        assert "DB-only" in text
        assert "Trading Bot" in text
        assert "preview" in text


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
