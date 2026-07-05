import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PREPARE_SCRIPT = ROOT / "scripts" / "prepare_rag_memory_promotion_review.py"
UPDATE_SCRIPT = ROOT / "scripts" / "update_rag_memory_promotion_status.py"
DOC = ROOT / "docs" / "rag_memory_promotion_gate.md"


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def memory(memory_id: str, status=None) -> dict:
    row = {
        "memory_id": memory_id,
        "question": f"Question for {memory_id}?",
        "answer_status": "ok",
        "evidence_strength": "db_grounded",
        "answer": f"DB-backed answer for {memory_id}.",
        "source_refs": [f"article_id:1:chunk_id:{memory_id}"],
        "used_sources": [{"source_ref": f"article_id:1:chunk_id:{memory_id}"}],
        "tags": ["rag_research", "db_only"],
    }
    if status is not None:
        row["promotion_status"] = status
    return row


def test_pending_or_missing_status_only_are_default_review_candidates(tmp_path):
    prepare = load_script(PREPARE_SCRIPT, "prepare_rag_memory_promotion_review")
    store = tmp_path / "memory.jsonl"
    write_jsonl(
        store,
        [
            memory("ragmem_pending", "pending"),
            memory("ragmem_missing"),
            memory("ragmem_legacy", "pending_human_review"),
            memory("ragmem_approved", "approved"),
            memory("ragmem_rejected", "rejected"),
        ],
    )

    summary, _json_path, _md_path = prepare.prepare_review(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    assert summary["candidate_count"] == 3
    assert [candidate["memory_id"] for candidate in summary["candidates"]] == [
        "ragmem_pending",
        "ragmem_missing",
        "ragmem_legacy",
    ]


def test_approved_and_rejected_are_excluded_from_default_review(tmp_path):
    prepare = load_script(PREPARE_SCRIPT, "prepare_rag_memory_promotion_review")
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_approved", "approved"), memory("ragmem_rejected", "rejected")])

    summary, _json_path, _md_path = prepare.prepare_review(
        memory_store_file=store,
        out_dir=tmp_path,
        timestamp="20260612-010203",
    )

    assert summary["candidate_count"] == 0
    assert summary["candidates"] == []


def test_limit_is_applied(tmp_path):
    prepare = load_script(PREPARE_SCRIPT, "prepare_rag_memory_promotion_review")
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_one", "pending"), memory("ragmem_two", "pending")])

    summary, _json_path, _md_path = prepare.prepare_review(
        memory_store_file=store,
        out_dir=tmp_path,
        limit=1,
        timestamp="20260612-010203",
    )

    assert summary["candidate_count"] == 1
    assert summary["candidates"][0]["memory_id"] == "ragmem_one"


def test_dry_run_does_not_write_review_reports(tmp_path):
    prepare = load_script(PREPARE_SCRIPT, "prepare_rag_memory_promotion_review")
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_pending", "pending")])

    summary, json_path, md_path = prepare.prepare_review(
        memory_store_file=store,
        out_dir=tmp_path,
        dry_run=True,
        timestamp="20260612-010203",
    )

    assert summary["candidate_count"] == 1
    assert json_path is None
    assert md_path is None
    assert not list(tmp_path.glob("rag-memory-promotion-review-*.json"))
    assert not list(tmp_path.glob("rag-memory-promotion-review-*.md"))


def test_review_reports_include_db_only_and_no_trading_bot_notices(tmp_path):
    prepare = load_script(PREPARE_SCRIPT, "prepare_rag_memory_promotion_review")
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_pending", "pending")])

    _summary, json_path, md_path = prepare.prepare_review(
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
        assert "Trading Bot" in text
        assert "must not be automatically exported" in text


def test_update_script_changes_status_to_pending_approved_and_rejected(tmp_path):
    updater = load_script(UPDATE_SCRIPT, "update_rag_memory_promotion_status")
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_status", "pending_human_review")])

    for status in ("pending", "approved", "rejected"):
        summary = updater.update_promotion_status(
            memory_store_file=store,
            memory_id="ragmem_status",
            status=status,
            note="reviewed",
            reviewer="tester",
            timestamp=f"20260612-01020{len(status)}",
        )
        row = read_jsonl(store)[0]
        assert summary["status"] == status
        assert row["promotion_status"] == status
        assert row["promotion_review"]["status"] == status
        assert row["promotion_review"]["note"] == "reviewed"
        assert row["promotion_review"]["reviewer"] == "tester"


def test_missing_memory_id_fails(tmp_path):
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_present", "pending")])

    result = subprocess.run(
        [
            sys.executable,
            str(UPDATE_SCRIPT),
            "--memory-store-file",
            str(store),
            "--memory-id",
            "ragmem_missing",
            "--status",
            "approved",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "memory_id not found" in result.stderr


def test_same_status_update_is_idempotent(tmp_path):
    updater = load_script(UPDATE_SCRIPT, "update_rag_memory_promotion_status")
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_idempotent", "pending")])

    updater.update_promotion_status(
        memory_store_file=store,
        memory_id="ragmem_idempotent",
        status="approved",
        note="looks useful",
        reviewer="tester",
        timestamp="20260612-010203",
    )
    first = store.read_text(encoding="utf-8")
    summary = updater.update_promotion_status(
        memory_store_file=store,
        memory_id="ragmem_idempotent",
        status="approved",
        note="looks useful",
        reviewer="tester",
        timestamp="20260612-040506",
    )
    second = store.read_text(encoding="utf-8")

    assert summary["changed"] is False
    assert first == second
    assert second.count("looks useful") == 1


def test_approved_status_does_not_create_or_modify_trading_bot_files(tmp_path):
    updater = load_script(UPDATE_SCRIPT, "update_rag_memory_promotion_status")
    store = tmp_path / "memory.jsonl"
    write_jsonl(store, [memory("ragmem_safe", "pending")])
    before = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")}

    updater.update_promotion_status(
        memory_store_file=store,
        memory_id="ragmem_safe",
        status="approved",
        timestamp="20260612-010203",
    )
    after = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")}

    assert before == after
    assert not any("trading" in name.lower() for name in after)


def test_no_external_web_naver_archive_write_or_trading_calls_are_added():
    combined = "\n".join(
        [
            PREPARE_SCRIPT.read_text(encoding="utf-8"),
            UPDATE_SCRIPT.read_text(encoding="utf-8"),
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
