import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diagnose_rulebook_gold_misses.py"


def load_script():
    spec = importlib.util.spec_from_file_location("diagnose_rulebook_gold_misses", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_rank_of_uses_exact_chunk_id():
    module = load_script()
    rows = [{"chunk_id": "20:0"}, {"chunk_id": "10:0"}]
    assert module.rank_of({"10:0"}, rows) == 2
    assert module.rank_of({"1:0"}, rows) is None


def test_dense_and_rerank_rows_keep_article_provenance():
    module = load_script()

    class Point:
        score = 0.75
        payload = {
            "chunk_id": "123:0",
            "article_id": 123,
            "title": "title",
            "text": "full evidence text",
        }

    dense = module.dense_row(Point(), 1)
    reranked = module.rerank_row(
        {
            "chunk_id": "123:0",
            "article_id": 123,
            "title": "title",
            "text": "full evidence text",
            "dense_score": 0.75,
            "rerank_score": 0.95,
        },
        1,
    )
    assert dense["chunk_id"] == reranked["chunk_id"] == "123:0"
    assert dense["article_id"] == reranked["article_id"] == 123
    assert reranked["rerank_score"] == 0.95
