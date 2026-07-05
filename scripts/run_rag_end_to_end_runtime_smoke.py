from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import draft_rag_approved_memory_rule_candidates as draft_candidates
import preview_rag_approved_memory_export as memory_preview
import preview_rag_trading_rule_export as trading_preview
import update_rag_memory_promotion_status as promotion_status
import update_rag_research_memory_store as memory_store
import update_rag_rule_candidate_registry as registry_update
import validate_rag_rule_candidate_drafts as draft_validator


DEFAULT_WORK_DIR_ROOT = PROJECT_ROOT / ".tmp" / "rag_e2e_runtime_smoke"
REPO_TMP_DIR = PROJECT_ROOT / ".tmp"
REPO_SMOKE_WORK_DIR_PREFIX = "rag_e2e_runtime_smoke"
FORBIDDEN_REPO_WORK_DIRS = (
    "data",
    "agent_reports",
    "scripts",
    "tests",
    "docs",
    "src",
    ".git",
    ".venv",
)
DB_ONLY_NOTICE = (
    "DB-only RAG end-to-end runtime smoke: use only synthetic fixtures and "
    "temporary work-dir artifacts. Do not use external web search, current "
    "market news, general economic knowledge, Naver Cafe access, archive "
    "writes, or archive.db/data mutations."
)
TRADING_BOT_NO_AUTO_APPLY_NOTICE = (
    "Trading Bot automatic application is prohibited: this smoke must not "
    "create, export, or modify Trading Bot rules or Trading Bot files."
)
RUNTIME_SMOKE_NOT_PRODUCTION_NOTICE = (
    "runtime-smoke-not-production: generated artifacts are fixture-based "
    "connectivity checks, not production RAG memory, not Trading Bot input, "
    "not a rule export, and not a trading signal."
)
FINAL_BOUNDARY_FRAGMENTS = (
    "DB-only",
    "Trading Bot automatic application is prohibited",
    "not a Trading Bot input file",
    "not a rule export",
    "not a trading signal",
)


class SmokeFailure(RuntimeError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(message)
        self.step = step


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def default_work_dir(timestamp: str) -> Path:
    return DEFAULT_WORK_DIR_ROOT / timestamp


def is_relative_to_path(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_safe_work_dir(work_dir: Path) -> Path:
    repo_root = PROJECT_ROOT.resolve()
    resolved_work_dir = work_dir.resolve()
    smoke_root = DEFAULT_WORK_DIR_ROOT.resolve()
    repo_tmp = REPO_TMP_DIR.resolve()
    temp_smoke_root = (Path(tempfile.gettempdir()) / "rag_e2e_runtime_smoke").resolve()

    if resolved_work_dir == repo_root:
        raise SmokeFailure("prepare_work_dir", f"unsafe work-dir rejected: {work_dir} is the repository root")

    for forbidden_name in FORBIDDEN_REPO_WORK_DIRS:
        forbidden = (repo_root / forbidden_name).resolve()
        if resolved_work_dir == forbidden or is_relative_to_path(resolved_work_dir, forbidden):
            raise SmokeFailure(
                "prepare_work_dir",
                f"unsafe work-dir rejected: {work_dir} is inside forbidden repository path {forbidden_name}",
            )

    repo_tmp_relative = None
    if is_relative_to_path(resolved_work_dir, repo_tmp):
        repo_tmp_relative = resolved_work_dir.relative_to(repo_tmp)
    is_repo_smoke_dir = is_relative_to_path(resolved_work_dir, smoke_root) or (
        repo_tmp_relative is not None
        and bool(repo_tmp_relative.parts)
        and repo_tmp_relative.parts[0].startswith(REPO_SMOKE_WORK_DIR_PREFIX)
    )
    if is_relative_to_path(resolved_work_dir, repo_root) and not is_repo_smoke_dir:
        raise SmokeFailure(
            "prepare_work_dir",
            f"unsafe work-dir rejected: repository work-dirs must use the .tmp/{REPO_SMOKE_WORK_DIR_PREFIX} smoke path",
        )
    if (
        not is_relative_to_path(resolved_work_dir, repo_root)
        and resolved_work_dir.exists()
        and not is_relative_to_path(resolved_work_dir, temp_smoke_root)
    ):
        raise SmokeFailure(
            "prepare_work_dir",
            "unsafe work-dir rejected: existing external work-dirs must be under the system temp smoke directory",
        )

    return resolved_work_dir


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            raw = line.strip()
            if raw:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}: expected JSON object rows")
                rows.append(value)
    return rows


def create_synthetic_inputs(work_dir: Path) -> tuple[Path, Path]:
    fixture_dir = work_dir / "fixtures"
    answer_file = fixture_dir / "synthetic-rag-research-answers.jsonl"
    learning_loop_file = fixture_dir / "synthetic-rag-learning-loop.json"
    answer_rows = [
        {
            "question_id": "smoke-q-001",
            "question": "Which DB-grounded condition should a reviewer watch in this synthetic fixture?",
            "answer_status": "answer_ok",
            "answer": (
                "Use the internal source text to watch for repeated liquidity-risk language before "
                "promoting a candidate. This is only a synthetic RAG smoke answer."
            ),
            "evidence_strength": "db_grounded",
            "source_refs": ["fixture://rag-smoke/source-001"],
            "used_sources": [
                {
                    "source_ref": "fixture://rag-smoke/source-001",
                    "title": "Synthetic RAG smoke source",
                    "chunk_id": "smoke-chunk-001",
                }
            ],
            "tags": ["rag_research", "db_only", "runtime_smoke", "watch_condition"],
            "topic": "runtime_smoke",
        }
    ]
    learning_loop = {
        "generated_at": "20260615-000000",
        "answer_file": str(answer_file),
        "retrieval_file": str(fixture_dir / "synthetic-rag-retrieval.jsonl"),
        "next_learning_candidates": [
            {
                "question_id": "smoke-q-001",
                "action": "candidate_for_memory_store",
                "reason": "Synthetic end-to-end smoke candidate.",
            }
        ],
        "db_only_notice": DB_ONLY_NOTICE,
    }
    write_jsonl(answer_file, answer_rows)
    write_json(learning_loop_file, learning_loop)
    return learning_loop_file, answer_file


def require_file(path: Path | None, step: str) -> Path:
    if path is None or not path.exists():
        raise SmokeFailure(step, f"expected output file was not created: {path}")
    return path


def require_count(value: int, step: str, name: str) -> None:
    if value < 1:
        raise SmokeFailure(step, f"{name} must be at least 1")


def approved_registry_draft(source_draft_file: Path, work_dir: Path) -> Path:
    report = read_json(source_draft_file)
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise SmokeFailure("prepare_approved_registry_draft", "draft report has no candidates")
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate["draft_status"] = "approved_for_registry"
    report["draft_candidates"] = report["candidates"]
    target = work_dir / "approved_for_registry" / source_draft_file.name.replace(".json", "-approved.json")
    write_json(target, report)
    return target


def final_boundary_text(report: dict[str, Any]) -> str:
    pieces = [
        report.get("db_only_notice"),
        report.get("trading_boundary_notice"),
        report.get("preview_not_export_notice"),
    ]
    for candidate in report.get("candidates") or []:
        if isinstance(candidate, dict):
            pieces.append(candidate.get("boundary_notice"))
            pieces.append(candidate.get("trading_export_preview_note"))
    return " ".join(str(piece or "") for piece in pieces)


def assert_final_preview_boundaries(report: dict[str, Any]) -> None:
    text = final_boundary_text(report)
    missing = [fragment for fragment in FINAL_BOUNDARY_FRAGMENTS if fragment not in text]
    if missing:
        raise SmokeFailure("verify_final_preview", f"final preview missing boundary fragments: {missing}")
    if not report.get("candidates"):
        raise SmokeFailure("verify_final_preview", "final preview has no candidates")


def build_summary(
    *,
    work_dir: Path,
    learning_loop_file: Path,
    answer_file: Path,
    memory_store_file: Path,
    approved_memory_preview_file: Path,
    rule_candidate_draft_file: Path,
    validation_result: dict[str, Any],
    registry_file: Path,
    trading_export_preview_file: Path,
    passed_steps: list[str],
    failed_step: str | None,
) -> dict[str, Any]:
    return {
        "work_dir": str(work_dir),
        "generated_input_files": [str(learning_loop_file), str(answer_file)],
        "memory_store_file": str(memory_store_file),
        "approved_memory_preview_file": str(approved_memory_preview_file),
        "rule_candidate_draft_file": str(rule_candidate_draft_file),
        "validation_result": validation_result,
        "registry_file": str(registry_file),
        "trading_export_preview_file": str(trading_export_preview_file),
        "passed_steps": passed_steps,
        "failed_step": failed_step,
        "db_only_notice": DB_ONLY_NOTICE,
        "trading_bot_no_auto_apply_notice": TRADING_BOT_NO_AUTO_APPLY_NOTICE,
        "runtime_smoke_not_production_notice": RUNTIME_SMOKE_NOT_PRODUCTION_NOTICE,
    }


def format_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG End-to-End Runtime Smoke",
        "",
        f"- work_dir: {summary['work_dir']}",
        f"- memory_store_file: {summary.get('memory_store_file', '(not created)')}",
        f"- approved_memory_preview_file: {summary.get('approved_memory_preview_file', '(not created)')}",
        f"- rule_candidate_draft_file: {summary.get('rule_candidate_draft_file', '(not created)')}",
        f"- registry_file: {summary.get('registry_file', '(not created)')}",
        f"- trading_export_preview_file: {summary.get('trading_export_preview_file', '(not created)')}",
        f"- failed_step: {summary['failed_step'] or 'none'}",
        f"- passed_steps: {json.dumps(summary['passed_steps'], ensure_ascii=True)}",
        "",
        "## Boundary",
        "",
        summary["db_only_notice"],
        "",
        summary["trading_bot_no_auto_apply_notice"],
        "",
        summary["runtime_smoke_not_production_notice"],
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_summary_reports(work_dir: Path, timestamp: str, summary: dict[str, Any]) -> tuple[Path, Path]:
    json_path = work_dir / f"rag-e2e-runtime-smoke-summary-{timestamp}.json"
    md_path = work_dir / f"rag-e2e-runtime-smoke-summary-{timestamp}.md"
    write_json(json_path, summary)
    md_path.write_text(format_markdown_summary(summary), encoding="utf-8", newline="\n")
    return json_path, md_path


def run_smoke(*, work_dir: Path | None = None, keep_artifacts: bool = False, timestamp: str | None = None) -> dict[str, Any]:
    stamp = timestamp or timestamp_now()
    requested_work_dir = work_dir or default_work_dir(stamp)
    try:
        resolved_work_dir = validate_safe_work_dir(requested_work_dir)
        if resolved_work_dir.exists() and not keep_artifacts:
            shutil.rmtree(resolved_work_dir)
        resolved_work_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise SmokeFailure("prepare_work_dir", str(exc)) from exc

    passed_steps: list[str] = []
    current_step = "startup"
    try:
        current_step = "create_synthetic_inputs"
        learning_loop_file, answer_file = create_synthetic_inputs(resolved_work_dir)
        passed_steps.append("create_synthetic_inputs")

        current_step = "update_memory_store"
        memory_store_file = resolved_work_dir / "memory" / "rag_research_memory_store.jsonl"
        memory_summary, _memory_summary_json, _memory_summary_md = memory_store.update_memory_store(
            learning_loop_file=learning_loop_file,
            answer_file=None,
            out_file=memory_store_file,
            timestamp=stamp,
        )
        require_count(memory_summary["added_count"], "update_memory_store", "added_count")
        passed_steps.append("update_memory_store")

        current_step = "approve_memory"
        memory_rows = read_jsonl(memory_store_file)
        memory_id = str(memory_rows[0]["memory_id"])
        promotion_status.update_promotion_status(
            memory_store_file=memory_store_file,
            memory_id=memory_id,
            status="approved",
            note="Synthetic runtime smoke approval.",
            reviewer="rag-runtime-smoke",
            timestamp=stamp,
        )
        passed_steps.append("approve_memory")

        current_step = "preview_approved_memory"
        preview_summary, preview_json, _preview_md = memory_preview.preview_export(
            memory_store_file=memory_store_file,
            out_dir=resolved_work_dir / "approved_memory_preview",
            timestamp=stamp,
        )
        require_count(preview_summary["approved_count"], "preview_approved_memory", "approved_count")
        approved_memory_preview_file = require_file(preview_json, "preview_approved_memory")
        passed_steps.append("preview_approved_memory")

        current_step = "draft_rule_candidates"
        draft_summary, draft_json, _draft_md = draft_candidates.draft_rule_candidates(
            preview_file=approved_memory_preview_file,
            out_dir=resolved_work_dir / "rule_candidate_draft",
            timestamp=stamp,
        )
        require_count(draft_summary["candidate_count"], "draft_rule_candidates", "candidate_count")
        rule_candidate_draft_file = require_file(draft_json, "draft_rule_candidates")
        passed_steps.append("draft_rule_candidates")

        current_step = "validate_rule_candidate_draft"
        validation_result, _validated_file = draft_validator.validate_draft_file(draft_file=rule_candidate_draft_file)
        if not validation_result.get("valid"):
            raise SmokeFailure("validate_rule_candidate_draft", "draft validation failed")
        passed_steps.append("validate_rule_candidate_draft")

        current_step = "prepare_approved_registry_draft"
        approved_draft_file = approved_registry_draft(rule_candidate_draft_file, resolved_work_dir)
        passed_steps.append("prepare_approved_registry_draft")

        current_step = "update_rule_candidate_registry"
        registry_file = resolved_work_dir / "registry" / "rag_rule_candidate_registry.jsonl"
        registry_summary, _registry_summary_json, _registry_summary_md = registry_update.update_registry(
            draft_file=approved_draft_file,
            registry_file=registry_file,
            out_dir=resolved_work_dir / "registry_update",
            timestamp=stamp,
        )
        require_count(registry_summary["added_count"], "update_rule_candidate_registry", "added_count")
        passed_steps.append("update_rule_candidate_registry")

        current_step = "preview_trading_export"
        trading_summary, trading_json, _trading_md = trading_preview.preview_export(
            registry_file=registry_file,
            out_dir=resolved_work_dir / "trading_export_preview",
            timestamp=stamp,
        )
        require_count(trading_summary["preview_count"], "preview_trading_export", "preview_count")
        trading_export_preview_file = require_file(trading_json, "preview_trading_export")
        assert_final_preview_boundaries(trading_summary)
        passed_steps.append("preview_trading_export")

        summary = build_summary(
            work_dir=resolved_work_dir,
            learning_loop_file=learning_loop_file,
            answer_file=answer_file,
            memory_store_file=memory_store_file,
            approved_memory_preview_file=approved_memory_preview_file,
            rule_candidate_draft_file=rule_candidate_draft_file,
            validation_result=validation_result,
            registry_file=registry_file,
            trading_export_preview_file=trading_export_preview_file,
            passed_steps=passed_steps,
            failed_step=None,
        )
        summary_json, summary_md = write_summary_reports(resolved_work_dir, stamp, summary)
        summary["summary_json"] = str(summary_json)
        summary["summary_md"] = str(summary_md)
        return summary
    except Exception as exc:
        if isinstance(exc, SmokeFailure):
            failed_step = exc.step
        else:
            failed_step = current_step
        failure_summary = {
            "work_dir": str(resolved_work_dir),
            "passed_steps": passed_steps,
            "failed_step": failed_step,
            "error": str(exc),
            "db_only_notice": DB_ONLY_NOTICE,
            "trading_bot_no_auto_apply_notice": TRADING_BOT_NO_AUTO_APPLY_NOTICE,
            "runtime_smoke_not_production_notice": RUNTIME_SMOKE_NOT_PRODUCTION_NOTICE,
        }
        write_summary_reports(resolved_work_dir, stamp, failure_summary)
        raise SmokeFailure(failed_step, str(exc)) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a fixture-based RAG 061-067 end-to-end runtime smoke.",
        epilog=f"{DB_ONLY_NOTICE} {TRADING_BOT_NO_AUTO_APPLY_NOTICE} {RUNTIME_SMOKE_NOT_PRODUCTION_NOTICE}",
    )
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv)
    try:
        summary = run_smoke(work_dir=args.work_dir, keep_artifacts=args.keep_artifacts, timestamp=args.timestamp)
    except SmokeFailure as exc:
        print(DB_ONLY_NOTICE)
        print(TRADING_BOT_NO_AUTO_APPLY_NOTICE)
        print(RUNTIME_SMOKE_NOT_PRODUCTION_NOTICE)
        print(f"FAILED step={exc.step}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(DB_ONLY_NOTICE)
        print(TRADING_BOT_NO_AUTO_APPLY_NOTICE)
        print(RUNTIME_SMOKE_NOT_PRODUCTION_NOTICE)
        print(f"FAILED step=startup: {exc}", file=sys.stderr)
        return 1
    print(DB_ONLY_NOTICE)
    print(TRADING_BOT_NO_AUTO_APPLY_NOTICE)
    print(RUNTIME_SMOKE_NOT_PRODUCTION_NOTICE)
    print("RAG end-to-end runtime smoke passed.")
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
