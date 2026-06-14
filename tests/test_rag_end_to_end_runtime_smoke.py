import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_rag_end_to_end_runtime_smoke.py"
DOC = ROOT / "docs" / "rag_end_to_end_runtime_smoke.md"
PRODUCTION_MEMORY_STORE = ROOT / "agent_reports" / "rag_research_memory_store.jsonl"
PRODUCTION_REGISTRY = ROOT / "agent_reports" / "rag_rule_candidate_registry.jsonl"


def safe_smoke_work_dir(tmp_path: Path, name: str) -> Path:
    return ROOT / ".tmp" / "rag_e2e_runtime_smoke" / "pytest" / tmp_path.name / name


def load_smoke():
    spec = importlib.util.spec_from_file_location("run_rag_end_to_end_runtime_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_signature(path: Path):
    if not path.exists():
        return None
    return (path.stat().st_size, path.read_bytes())


def test_runtime_smoke_succeeds_in_tmp_work_dir(tmp_path):
    smoke = load_smoke()
    work_dir = safe_smoke_work_dir(tmp_path, "smoke")

    summary = smoke.run_smoke(work_dir=work_dir, timestamp="20260615-010203")

    assert summary["failed_step"] is None
    assert "preview_trading_export" in summary["passed_steps"]
    assert Path(summary["memory_store_file"]).is_file()
    assert Path(summary["approved_memory_preview_file"]).is_file()
    assert Path(summary["rule_candidate_draft_file"]).is_file()
    assert Path(summary["registry_file"]).is_file()
    final_preview_file = Path(summary["trading_export_preview_file"])
    assert final_preview_file.is_file()
    assert Path(summary["summary_json"]).is_file()
    assert Path(summary["summary_md"]).is_file()

    final_preview = read_json(final_preview_file)
    assert final_preview["preview_count"] >= 1
    assert final_preview["candidates"]
    assert final_preview["candidates"][0]["export_preview_status"] == "preview_needs_human_review"


def test_runtime_smoke_does_not_write_production_memory_or_registry(tmp_path):
    smoke = load_smoke()
    before_memory = file_signature(PRODUCTION_MEMORY_STORE)
    before_registry = file_signature(PRODUCTION_REGISTRY)

    summary = smoke.run_smoke(work_dir=safe_smoke_work_dir(tmp_path, "isolated"), timestamp="20260615-010204")

    assert Path(summary["memory_store_file"]) != PRODUCTION_MEMORY_STORE
    assert Path(summary["registry_file"]) != PRODUCTION_REGISTRY
    assert file_signature(PRODUCTION_MEMORY_STORE) == before_memory
    assert file_signature(PRODUCTION_REGISTRY) == before_registry


def test_final_preview_preserves_boundary_language(tmp_path):
    smoke = load_smoke()
    summary = smoke.run_smoke(work_dir=safe_smoke_work_dir(tmp_path, "boundary"), timestamp="20260615-010205")
    final_preview = read_json(Path(summary["trading_export_preview_file"]))
    combined = " ".join(
        [
            final_preview["db_only_notice"],
            final_preview["trading_boundary_notice"],
            final_preview["preview_not_export_notice"],
            final_preview["candidates"][0]["boundary_notice"],
            final_preview["candidates"][0]["trading_export_preview_note"],
            summary["runtime_smoke_not_production_notice"],
        ]
    )

    assert "DB-only" in combined
    assert "Trading Bot automatic application is prohibited" in combined
    assert "not a Trading Bot input file" in combined
    assert "not a rule export" in combined
    assert "not a trading signal" in combined
    assert "runtime-smoke-not-production" in combined


def test_runtime_smoke_creates_no_trading_execution_signal_fields(tmp_path):
    smoke = load_smoke()
    work_dir = safe_smoke_work_dir(tmp_path, "execution-boundary")
    summary = smoke.run_smoke(work_dir=work_dir, timestamp="20260615-010206")
    final_preview = read_json(Path(summary["trading_export_preview_file"]))
    forbidden_fields = {"buy", "sell", "entry", "exit", "order", "position", "final_rule_status"}

    for candidate in final_preview["candidates"]:
        assert forbidden_fields.isdisjoint(candidate)
        candidate_text = json.dumps(candidate, ensure_ascii=True).lower()
        assert "final rule" not in candidate_text

    generated_files = [path.name.lower() for path in work_dir.rglob("*") if path.is_file()]
    assert not any("trading-bot-input" in name or "trading_bot_input" in name for name in generated_files)
    assert not any("final-rule" in name or "final_rule" in name for name in generated_files)


def test_missing_intermediate_file_fails_with_clear_step(tmp_path, monkeypatch):
    smoke = load_smoke()
    original_create = smoke.create_synthetic_inputs

    def broken_create(work_dir):
        learning_loop_file, answer_file = original_create(work_dir)
        answer_file.unlink()
        return learning_loop_file, answer_file

    monkeypatch.setattr(smoke, "create_synthetic_inputs", broken_create)

    try:
        smoke.run_smoke(work_dir=safe_smoke_work_dir(tmp_path, "broken"), timestamp="20260615-010207")
    except smoke.SmokeFailure as exc:
        assert exc.step == "update_memory_store"
        assert "No such file" in str(exc) or "cannot find" in str(exc)
    else:
        raise AssertionError("expected SmokeFailure")

    failure_summary = read_json(
        safe_smoke_work_dir(tmp_path, "broken") / "rag-e2e-runtime-smoke-summary-20260615-010207.json"
    )
    assert failure_summary["failed_step"] == "update_memory_store"


def test_cli_missing_intermediate_file_failure_is_non_zero(tmp_path):
    missing_parent = tmp_path / "missing-parent" / "child"
    blocker = tmp_path / "missing-parent"
    blocker.write_text("not a directory", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--work-dir",
            str(missing_parent),
            "--timestamp",
            "20260615-010208",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "FAILED step=" in result.stderr


def test_docs_help_and_summary_include_boundaries(tmp_path):
    smoke = load_smoke()
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    summary = smoke.run_smoke(work_dir=safe_smoke_work_dir(tmp_path, "docs"), timestamp="20260615-010209")
    summary_text = Path(summary["summary_md"]).read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8")
    combined = "\n".join([help_result.stdout, summary_text, doc_text])

    assert help_result.returncode == 0
    assert "DB-only" in combined
    assert "Trading Bot automatic application is prohibited" in combined
    assert "runtime-smoke-not-production" in combined
    assert "not a trading signal" in combined


def test_static_boundaries_no_external_or_forbidden_calls():
    script_text = SCRIPT.read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8")
    combined = script_text + "\n" + doc_text
    forbidden_fragments = [
        "requests.",
        "urllib.",
        "http://",
        "https://",
        "naver.com",
        "cafe.naver",
        "daily_archive.py",
        "batch_recollect.py",
        "index_tail.py",
        "_step3_verify_v2.py",
        "src/browser.py",
        "src/parser.py",
        "src/collector.py",
        "src/indexer.py",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in script_text
    assert "archive.db" in combined
    assert "Trading Bot files" in combined
    assert "fixture" in combined


def test_repo_root_or_dot_work_dir_is_rejected_and_not_deleted():
    smoke = load_smoke()
    before = file_signature(SCRIPT)

    for unsafe in (ROOT, Path(".")):
        try:
            smoke.run_smoke(work_dir=unsafe, timestamp="20260615-010210")
        except smoke.SmokeFailure as exc:
            assert exc.step == "prepare_work_dir"
            assert "unsafe work-dir rejected" in str(exc)
        else:
            raise AssertionError(f"expected unsafe work-dir rejection for {unsafe}")

    assert file_signature(SCRIPT) == before


def test_agent_reports_and_data_work_dirs_are_rejected_and_not_deleted(tmp_path):
    smoke = load_smoke()
    temp_repo = tmp_path / "repo"
    temp_repo.mkdir()
    for name in ("agent_reports", "data"):
        protected = temp_repo / name
        protected.mkdir()
        (protected / "sentinel.txt").write_text("keep", encoding="utf-8")

    old_project_root = smoke.PROJECT_ROOT
    old_default_work_dir_root = smoke.DEFAULT_WORK_DIR_ROOT
    smoke.PROJECT_ROOT = temp_repo
    smoke.DEFAULT_WORK_DIR_ROOT = temp_repo / ".tmp" / "rag_e2e_runtime_smoke"
    try:
        for name in ("agent_reports", "data"):
            try:
                smoke.run_smoke(work_dir=temp_repo / name, timestamp="20260615-010211")
            except smoke.SmokeFailure as exc:
                assert exc.step == "prepare_work_dir"
                assert "unsafe work-dir rejected" in str(exc)
            else:
                raise AssertionError(f"expected unsafe work-dir rejection for {name}")
            assert (temp_repo / name / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    finally:
        smoke.PROJECT_ROOT = old_project_root
        smoke.DEFAULT_WORK_DIR_ROOT = old_default_work_dir_root


def test_repo_tmp_smoke_work_dir_is_allowed(tmp_path):
    smoke = load_smoke()
    work_dir = safe_smoke_work_dir(tmp_path, "allowed-case")

    summary = smoke.run_smoke(work_dir=work_dir, timestamp="20260615-010212")

    assert Path(summary["work_dir"]).resolve() == work_dir.resolve()
    assert Path(summary["trading_export_preview_file"]).is_file()


def test_keep_artifacts_does_not_allow_forbidden_work_dir(tmp_path):
    smoke = load_smoke()
    temp_repo = tmp_path / "repo"
    protected = temp_repo / "docs"
    protected.mkdir(parents=True)
    (protected / "sentinel.txt").write_text("keep", encoding="utf-8")

    old_project_root = smoke.PROJECT_ROOT
    old_default_work_dir_root = smoke.DEFAULT_WORK_DIR_ROOT
    smoke.PROJECT_ROOT = temp_repo
    smoke.DEFAULT_WORK_DIR_ROOT = temp_repo / ".tmp" / "rag_e2e_runtime_smoke"
    try:
        try:
            smoke.run_smoke(work_dir=protected, keep_artifacts=True, timestamp="20260615-010213")
        except smoke.SmokeFailure as exc:
            assert exc.step == "prepare_work_dir"
            assert "unsafe work-dir rejected" in str(exc)
        else:
            raise AssertionError("expected unsafe work-dir rejection with keep_artifacts")
        assert (protected / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    finally:
        smoke.PROJECT_ROOT = old_project_root
        smoke.DEFAULT_WORK_DIR_ROOT = old_default_work_dir_root
