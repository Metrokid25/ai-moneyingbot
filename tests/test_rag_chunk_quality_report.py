import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "report_rag_chunk_quality.py"


def load_reporter():
    spec = importlib.util.spec_from_file_location("report_rag_chunk_quality", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def metadata(chunk_id: str, article_id: int, content_hash: str) -> dict:
    return {
        "article_id": article_id,
        "source_id": str(article_id),
        "source_path": f"https://example.test/{article_id}",
        "chunk_id": chunk_id,
        "chunk_index": int(chunk_id.split(":")[1]),
        "posted_at": "2026.05.20.",
        "created_at": "2026.05.20.",
        "collected_at": "2026-05-20T09:00:00+09:00",
        "year": 2026,
        "month": 5,
        "title": "sample",
        "body_len": 100,
        "author": "tester",
        "source": "fixture",
        "url": f"https://example.test/{article_id}",
        "source_url": f"https://example.test/{article_id}",
        "content_hash": content_hash,
        "status": "BODY_COLLECTED",
    }


def test_build_quality_report_detects_chunk_issues():
    reporter = load_reporter()
    chunks = [
        {
            "chunk_id": "1:0",
            "article_id": 1,
            "chunk_index": 0,
            "embedding_text": "",
            "metadata": metadata("1:0", 1, "hash-a"),
        },
        {
            "chunk_id": "2:0",
            "article_id": 2,
            "chunk_index": 0,
            "embedding_text": "short",
            "metadata": {"chunk_id": "2:0"},
        },
        {
            "chunk_id": "3:0",
            "article_id": 3,
            "chunk_index": 0,
            "embedding_text": "x" * 51,
            "metadata": metadata("3:0", 3, "hash-dup"),
        },
        {
            "chunk_id": "4:0",
            "article_id": 4,
            "chunk_index": 0,
            "embedding_text": "valid chunk text",
            "metadata": metadata("4:0", 4, "hash-dup"),
        },
    ]

    report = reporter.build_quality_report(chunks, min_chars=10, max_chars=50)

    assert report["issue_counts"] == {
        "empty_chunks": 1,
        "too_short_chunks": 1,
        "too_long_chunks": 1,
        "missing_metadata_chunks": 1,
        "duplicate_chunk_ids": 0,
        "duplicate_source_candidates": 1,
    }
    assert report["empty_chunks"] == ["1:0"]
    assert report["too_short_chunks"] == [{"chunk_id": "2:0", "length": 5}]
    assert report["too_long_chunks"] == [{"chunk_id": "3:0", "length": 51}]
    assert report["missing_metadata_chunks"][0]["chunk_id"] == "2:0"
    assert report["duplicate_source_candidates"] == [
        {"source": "content_hash:hash-dup", "count": 2}
    ]


def test_cli_writes_json_report_to_explicit_output_path(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    report_path = tmp_path / "quality" / "report.json"
    write_jsonl(
        chunks_path,
        [
            {
                "chunk_id": "1:0",
                "article_id": 1,
                "chunk_index": 0,
                "embedding_text": "readable chunk text",
                "metadata": metadata("1:0", 1, "hash-a"),
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--chunks-path",
            str(chunks_path),
            "--format",
            "json",
            "--out-path",
            str(report_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Report written to" in result.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["total_chunks"] == 1
    assert report["issue_counts"]["empty_chunks"] == 0


def test_cli_prints_text_report_to_stdout(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    write_jsonl(
        chunks_path,
        [
            {
                "chunk_id": "1:0",
                "article_id": 1,
                "chunk_index": 0,
                "embedding_text": "readable chunk text",
                "metadata": metadata("1:0", 1, "hash-a"),
            }
        ],
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--chunks-path", str(chunks_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "=== RAG chunk quality report ===" in result.stdout
    assert "empty_chunks: 0" in result.stdout
