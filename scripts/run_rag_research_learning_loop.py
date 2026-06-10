from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "agent_reports"
DEFAULT_COLLECTION = "goodmorning_chunks"
DEFAULT_TOP_K = 5
JSONL_LABEL = "JSONL:"
DB_ONLY_NOTICE = (
    "DB-only learning loop: use only local question JSONL, Qdrant retrieval reports, "
    "and generated answer reports. Do not use external web search, current market news, "
    "general economic knowledge, Naver Cafe access, archive writes, or Trading Bot rule changes."
)


class CommandResult(NamedTuple):
    display: str
    returncode: int
    stdout: str
    stderr: str


class LearningPlan(NamedTuple):
    retrieval_command: tuple[str, ...] | None
    answer_command: tuple[str, ...]
    retrieval_file: Path | None


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: row must be a JSON object")
            rows.append(row)
    return rows


def count_status(rows: Sequence[dict[str, Any]], field: str, status: str) -> int:
    return sum(1 for row in rows if row.get(field) == status)


def ids_for_status(rows: Sequence[dict[str, Any]], field: str, status: str) -> list[str]:
    return [
        str(row.get("question_id"))
        for row in rows
        if row.get(field) == status and row.get("question_id") not in (None, "")
    ]


def parse_jsonl_path(output: str) -> Path:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(JSONL_LABEL):
            return Path(stripped.removeprefix(JSONL_LABEL).strip())
    raise ValueError("runner output did not include a JSONL report path")


def run_command(argv: Sequence[str]) -> CommandResult:
    display = " ".join(str(part) for part in argv)
    result = subprocess.run(
        list(argv),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return CommandResult(display, int(result.returncode), result.stdout, result.stderr)


def build_retrieval_command(args: argparse.Namespace, stamp: str) -> tuple[str, ...]:
    if args.questions_file is None:
        raise ValueError("--questions-file is required when --retrieval-file is not supplied")
    command = [
        sys.executable,
        "scripts/run_rag_research_retrieval.py",
        "--questions-file",
        str(args.questions_file),
        "--top-k",
        str(args.top_k),
        "--collection",
        args.collection,
        "--out-dir",
        str(args.out_dir),
        "--timestamp",
        stamp,
    ]
    if args.qdrant_path is not None:
        command.extend(["--qdrant-path", str(args.qdrant_path)])
    return tuple(command)


def build_answer_command(retrieval_file: Path, out_dir: Path, stamp: str) -> tuple[str, ...]:
    return (
        sys.executable,
        "scripts/run_rag_research_answers.py",
        "--retrieval-file",
        str(retrieval_file),
        "--out-dir",
        str(out_dir),
        "--timestamp",
        stamp,
    )


def build_learning_plan(args: argparse.Namespace, stamp: str) -> LearningPlan:
    if args.retrieval_file is not None:
        retrieval_file = args.retrieval_file
        retrieval_command = None
    else:
        retrieval_file = None
        retrieval_command = build_retrieval_command(args, stamp)
    answer_input = retrieval_file if retrieval_file is not None else Path("<retrieval report from previous step>")
    return LearningPlan(
        retrieval_command=retrieval_command,
        answer_command=build_answer_command(answer_input, args.out_dir, stamp),
        retrieval_file=retrieval_file,
    )


def next_learning_candidates(
    answer_records: Sequence[dict[str, Any]],
    *,
    backend_unavailable: bool,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for question_id in ids_for_status(answer_records, "answer_status", "weak_evidence"):
        candidates.append({"question_id": question_id, "action": "needs_better_evidence"})
    for question_id in ids_for_status(answer_records, "answer_status", "no_evidence"):
        candidates.append({"question_id": question_id, "action": "needs_retrieval_query_refinement"})
    for question_id in ids_for_status(answer_records, "answer_status", "ok"):
        candidates.append({"question_id": question_id, "action": "candidate_for_memory_store"})
    if backend_unavailable:
        backend_ids = ids_for_status(answer_records, "answer_status", "backend_unavailable")
        if backend_ids:
            for question_id in backend_ids:
                candidates.append({"question_id": question_id, "action": "fix_retrieval_backend_before_learning"})
        else:
            candidates.append({"question_id": "*", "action": "fix_retrieval_backend_before_learning"})
    return candidates


def summarize_learning_loop(
    *,
    questions_file: Path | None,
    retrieval_file: Path,
    answer_file: Path,
    retrieval_records: Sequence[dict[str, Any]],
    answer_records: Sequence[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    answer_backend_unavailable = count_status(answer_records, "answer_status", "backend_unavailable")
    retrieval_backend_unavailable = count_status(retrieval_records, "retrieval_status", "backend_unavailable")
    backend_statuses = sorted({str(row.get("backend_status")) for row in retrieval_records if row.get("backend_status")})
    backend_unavailable = bool(
        answer_backend_unavailable
        or retrieval_backend_unavailable
        or any(status in {"unavailable", "empty_collection"} for status in backend_statuses)
    )
    question_count = max(len(retrieval_records), len(answer_records))
    summary = {
        "generated_at": generated_at,
        "db_only": True,
        "db_only_notice": DB_ONLY_NOTICE,
        "questions_file": str(questions_file) if questions_file is not None else None,
        "retrieval_file": str(retrieval_file),
        "answer_file": str(answer_file),
        "backend_status": "backend_unavailable" if backend_unavailable else "ok",
        "backend_statuses": backend_statuses,
        "question_count": question_count,
        "retrieval_ok": count_status(retrieval_records, "retrieval_status", "ok"),
        "retrieval_no_results": count_status(retrieval_records, "retrieval_status", "no_results"),
        "retrieval_backend_unavailable": retrieval_backend_unavailable,
        "answer_ok": count_status(answer_records, "answer_status", "ok"),
        "answer_weak_evidence": count_status(answer_records, "answer_status", "weak_evidence"),
        "answer_no_evidence": count_status(answer_records, "answer_status", "no_evidence"),
        "answer_backend_unavailable": answer_backend_unavailable,
        "weak_evidence_question_ids": ids_for_status(answer_records, "answer_status", "weak_evidence"),
        "no_evidence_question_ids": ids_for_status(answer_records, "answer_status", "no_evidence"),
        "backend_unavailable": backend_unavailable,
    }
    candidates = next_learning_candidates(answer_records, backend_unavailable=backend_unavailable)
    summary["next_learning_candidates"] = candidates
    summary["next_actions"] = sorted({candidate["action"] for candidate in candidates})
    return summary


def format_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# RAG Autonomous Research Learning Loop Report",
        "",
        f"- generated_at: {summary['generated_at']}",
        "- db_only: true",
        f"- questions_file: {summary.get('questions_file')}",
        f"- retrieval_file: {summary.get('retrieval_file')}",
        f"- answer_file: {summary.get('answer_file')}",
        f"- backend_status: {summary.get('backend_status')}",
        f"- question_count: {summary.get('question_count')}",
        f"- retrieval_ok: {summary.get('retrieval_ok')}",
        f"- retrieval_no_results: {summary.get('retrieval_no_results')}",
        f"- retrieval_backend_unavailable: {summary.get('retrieval_backend_unavailable')}",
        f"- answer_ok: {summary.get('answer_ok')}",
        f"- answer_weak_evidence: {summary.get('answer_weak_evidence')}",
        f"- answer_no_evidence: {summary.get('answer_no_evidence')}",
        f"- answer_backend_unavailable: {summary.get('answer_backend_unavailable')}",
        f"- backend_unavailable: {str(summary.get('backend_unavailable')).lower()}",
        "",
        "## DB-only Safety",
        "",
        DB_ONLY_NOTICE,
        "",
        "## Weak Evidence Questions",
        "",
    ]
    weak_ids = summary.get("weak_evidence_question_ids") or []
    lines.extend([f"- {question_id}" for question_id in weak_ids] or ["- none"])
    lines.extend(["", "## No Evidence Questions", ""])
    no_ids = summary.get("no_evidence_question_ids") or []
    lines.extend([f"- {question_id}" for question_id in no_ids] or ["- none"])
    lines.extend(["", "## Next Learning Candidates", ""])
    candidates = summary.get("next_learning_candidates") or []
    if candidates:
        lines.extend(["| question_id | action |", "| --- | --- |"])
        for candidate in candidates:
            lines.append(f"| {candidate.get('question_id')} | {candidate.get('action')} |")
    else:
        lines.append("No next learning candidates were generated.")
    lines.extend(["", "## Next Actions", ""])
    actions = summary.get("next_actions") or []
    lines.extend([f"- {action}" for action in actions] or ["- none"])
    return "\n".join(lines).rstrip() + "\n"


def write_reports(out_dir: Path, stamp: str, summary: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"rag-learning-loop-{stamp}.json"
    md_path = out_dir / f"rag-learning-loop-{stamp}.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_report(summary), encoding="utf-8", newline="\n")
    return json_path, md_path


def print_plan(plan: LearningPlan) -> None:
    print(DB_ONLY_NOTICE)
    print("Dry run: planned commands only; no reports are generated.")
    if plan.retrieval_command is None:
        print("Retrieval step: skipped because --retrieval-file was supplied")
    else:
        print("Retrieval step:")
        print("  " + " ".join(plan.retrieval_command))
    print("Answer step:")
    print("  " + " ".join(plan.answer_command))
    print("Learning summary step: read retrieval/answer JSONL and write rag-learning-loop reports")


def run_learning_loop(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path]:
    stamp = args.timestamp or timestamp_now()
    retrieval_file = args.retrieval_file
    if retrieval_file is None:
        retrieval_command = build_retrieval_command(args, stamp)
        result = run_command(retrieval_command)
        if result.returncode != 0:
            raise RuntimeError(f"retrieval step failed with exit code {result.returncode}")
        retrieval_file = parse_jsonl_path(result.stdout)
    answer_command = build_answer_command(retrieval_file, args.out_dir, stamp)
    answer_result = run_command(answer_command)
    if answer_result.returncode != 0:
        raise RuntimeError(f"answer step failed with exit code {answer_result.returncode}")
    answer_file = parse_jsonl_path(answer_result.stdout)

    retrieval_records = read_jsonl(retrieval_file)
    answer_records = read_jsonl(answer_file)
    summary = summarize_learning_loop(
        questions_file=args.questions_file,
        retrieval_file=retrieval_file,
        answer_file=answer_file,
        retrieval_records=retrieval_records,
        answer_records=answer_records,
        generated_at=stamp,
    )
    json_path, md_path = write_reports(args.out_dir, stamp, summary)
    return summary, json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a DB-only autonomous RAG research learning loop by orchestrating existing "
            "question retrieval and answer draft runners. No external web/current market "
            "knowledge is used."
        ),
        epilog=DB_ONLY_NOTICE,
    )
    parser.add_argument("--questions-file", type=Path, default=None)
    parser.add_argument("--retrieval-file", type=Path, default=None)
    parser.add_argument("--qdrant-path", type=Path, default=None)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)
    if args.retrieval_file is None and args.questions_file is None:
        parser.error("--questions-file is required unless --retrieval-file is supplied")
    return args


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    try:
        args = parse_args(argv)
        stamp = args.timestamp or timestamp_now()
        plan = build_learning_plan(args, stamp)
        if args.dry_run:
            print_plan(plan)
            return 0
        summary, json_path, md_path = run_learning_loop(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("RAG DB-only research learning loop completed")
    print(f"Questions: {summary.get('question_count')}")
    print(f"Answer ok: {summary.get('answer_ok')}")
    print(f"Weak evidence: {summary.get('answer_weak_evidence')}")
    print(f"No evidence: {summary.get('answer_no_evidence')}")
    print(f"Backend unavailable: {summary.get('backend_unavailable')}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
