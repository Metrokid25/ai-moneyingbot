import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS_PATH = PROJECT_ROOT / "tests" / "fixtures" / "rag_eval_questions.jsonl"
PASS_THRESHOLD = 0.3


class EvaluationInputError(ValueError):
    pass


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise EvaluationInputError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise EvaluationInputError(f"{path}:{line_number}: row must be a JSON object")
            records.append(record)
    return records


def require_list(record: dict[str, Any], field: str) -> None:
    if not isinstance(record.get(field), list):
        raise EvaluationInputError(f"{record.get('id', '<unknown>')}: {field} must be a list")


def validate_question_record(record: dict[str, Any]) -> None:
    for field in ("id", "question", "category"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise EvaluationInputError(f"{field} is required")

    for field in ("expected_topics", "expected_keywords", "expected_article_ids", "expected_chunk_ids"):
        require_list(record, field)

    date_range = record.get("expected_date_range")
    if date_range is not None and not isinstance(date_range, dict):
        raise EvaluationInputError(f"{record['id']}: expected_date_range must be an object or null")


def validate_questions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for record in records:
        validate_question_record(record)
        record_id = record["id"]
        if record_id in seen:
            raise EvaluationInputError(f"duplicate id: {record_id}")
        seen.add(record_id)
    return records


def load_questions(path: Path) -> list[dict[str, Any]]:
    return validate_questions(read_jsonl(path))


def validate_mock_result_record(record: dict[str, Any]) -> None:
    if not isinstance(record.get("id"), str) or not record["id"].strip():
        raise EvaluationInputError("mock result id is required")
    if not isinstance(record.get("results"), list):
        raise EvaluationInputError(f"{record['id']}: results must be a list")


def load_mock_results(path: Path) -> dict[str, list[dict[str, Any]]]:
    rows = read_jsonl(path)
    results_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        validate_mock_result_record(row)
        record_id = row["id"]
        if record_id in results_by_id:
            raise EvaluationInputError(f"duplicate mock result id: {record_id}")
        results_by_id[record_id] = [result for result in row["results"] if isinstance(result, dict)]
    return results_by_id


def normalize_text(value: Any) -> str:
    return str(value or "").casefold()


def result_search_text(result: dict[str, Any]) -> str:
    return " ".join(
        [
            normalize_text(result.get("title")),
            normalize_text(result.get("snippet")),
            normalize_text(result.get("text")),
        ]
    )


def score_question(question: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    keywords = [str(keyword) for keyword in question.get("expected_keywords", [])]
    search_text = "\n".join(result_search_text(result) for result in results)
    hits = [keyword for keyword in keywords if normalize_text(keyword) in search_text]
    hit_count = len(hits)
    hit_rate = hit_count / len(keywords) if keywords else None
    top_score = results[0].get("score") if results else None

    if hit_rate is None:
        passed: bool | None = None
    else:
        passed = hit_rate >= PASS_THRESHOLD

    return {
        "id": question["id"],
        "category": question["category"],
        "keyword_hit_count": hit_count,
        "keyword_hit_rate": hit_rate,
        "matched_keywords": hits,
        "retrieved_count": len(results),
        "top_score": top_score,
        "pass": passed,
    }


def evaluate_mock_results(
    questions: list[dict[str, Any]],
    mock_results: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [score_question(question, mock_results.get(question["id"], [])) for question in questions]


def build_summary(questions: list[dict[str, Any]], scores: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for score in scores if score["pass"] is True)
    failed = sum(1 for score in scores if score["pass"] is False)
    skipped = sum(1 for score in scores if score["pass"] is None)
    return {
        "question_count": len(questions),
        "evaluated_count": len(scores),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "api_calls": False,
        "qdrant_search": False,
    }


def print_text_summary(summary: dict[str, Any], scores: list[dict[str, Any]]) -> None:
    print("RAG retrieval evaluation dry-run")
    print(f"questions: {summary['question_count']}")
    print(f"evaluated: {summary['evaluated_count']}")
    print(f"passed: {summary['passed']}")
    print(f"failed: {summary['failed']}")
    print(f"skipped: {summary['skipped']}")
    print("api_calls: false")
    print("qdrant_search: false")
    for score in scores:
        hit_rate = score["keyword_hit_rate"]
        rendered_rate = "skipped" if hit_rate is None else f"{hit_rate:.3f}"
        print(
            f"- {score['id']}: hits={score['keyword_hit_count']} "
            f"rate={rendered_rate} retrieved={score['retrieved_count']} pass={score['pass']}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and score a RAG retrieval evaluation set without API or Qdrant calls.",
    )
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_PATH)
    parser.add_argument("--mock-results", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and score mock results only.")
    parser.add_argument("--execute", action="store_true", help="Reserved for future real retrieval evaluation.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.execute:
        print("error: --execute real retrieval evaluation is not implemented yet", file=sys.stderr)
        return 2

    try:
        questions = load_questions(args.questions)
        mock_results = load_mock_results(args.mock_results) if args.mock_results else {}
        scores = evaluate_mock_results(questions, mock_results) if args.mock_results else []
    except EvaluationInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    summary = build_summary(questions, scores)
    payload = {"summary": summary, "scores": scores}
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text_summary(summary, scores)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
