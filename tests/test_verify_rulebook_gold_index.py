import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_rulebook_gold_index.py"


def load_script():
    spec = importlib.util.spec_from_file_location("verify_rulebook_gold_index", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Point:
    def __init__(self, payload):
        self.payload = payload


def test_summary_passes_only_with_chunk_article_and_text():
    module = load_script()
    points = [
        Point({"chunk_id": "10:0", "article_id": 10, "text": "evidence"}),
        Point({"chunk_id": "20:1", "article_id": 20, "text": "other evidence"}),
    ]
    summary = module.summarize_points(["10:0", "20:1"], points)
    assert summary["validation"] == "passed"
    assert summary["retrieved_chunk_count"] == 2


def test_summary_reports_each_failure_class():
    module = load_script()
    points = [
        Point({"chunk_id": "10:0", "article_id": 99, "text": "evidence"}),
        Point({"chunk_id": "20:0", "article_id": 20, "text": ""}),
    ]
    summary = module.summarize_points(["10:0", "20:0", "30:0"], points)
    assert summary["validation"] == "failed"
    assert summary["missing_chunk_ids"] == ["30:0"]
    assert summary["article_id_mismatch_chunk_ids"] == ["10:0"]
    assert summary["empty_text_chunk_ids"] == ["20:0"]
