import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "generate_rag_research_questions.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_rag_research_questions", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def sample_chunk(article_id: int, chunk_id: str, title: str, text: str) -> dict:
    return {
        "article_id": article_id,
        "chunk_id": chunk_id,
        "embedding_text": text,
        "metadata": {
            "article_id": article_id,
            "chunk_id": chunk_id,
            "title": title,
        },
    }


def test_build_research_questions_uses_only_internal_rows():
    generator = load_generator()
    chunks = [
        sample_chunk(
            1001,
            "1001:0",
            "Rates and stocks",
            "Higher rates can pressure equity valuations through discount rates.",
        ),
        sample_chunk(
            1002,
            "1002:0",
            "FX watch",
            "A stronger dollar can affect foreign flows into Korean equities.",
        ),
    ]
    eval_path = Path("internal_eval.jsonl")
    eval_rows = [
        {
            "id": "golden-001",
            "question": "How do higher rates pressure equity valuations?",
            "category": "rates",
            "expected_topics": ["higher rates", "equity valuations"],
            "expected_keywords": ["higher rates", "discount rates"],
        }
    ]

    questions = generator.build_research_questions(chunks, {eval_path: eval_rows}, 5)

    assert questions
    assert all(question["db_only"] is True for question in questions)
    assert all(question["status"] == "candidate" for question in questions)
    assert all(question["source_refs"] for question in questions)
    assert any("existing_eval" in question["generated_from"] for question in questions)
    assert any("chunk_keyword" in question["generated_from"] for question in questions)
    assert any("1001:0" in ref for question in questions for ref in question["source_refs"])


def test_cli_writes_markdown_and_jsonl_reports(tmp_path):
    chunks_path = tmp_path / "chunks.jsonl"
    eval_path = tmp_path / "eval.jsonl"
    out_dir = tmp_path / "reports"
    write_jsonl(
        chunks_path,
        [
            sample_chunk(
                1001,
                "1001:0",
                "Rates and stocks",
                "Higher rates can pressure equity valuations through discount rates.",
            )
        ],
    )
    write_jsonl(
        eval_path,
        [
            {
                "id": "golden-001",
                "question": "How do higher rates pressure equity valuations?",
                "category": "rates",
                "expected_topics": ["higher rates", "equity valuations"],
                "expected_keywords": ["higher rates", "discount rates"],
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--chunks-path",
            str(chunks_path),
            "--eval-path",
            str(eval_path),
            "--out-dir",
            str(out_dir),
            "--timestamp",
            "20260601-010203",
            "--max-questions",
            "4",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    jsonl_path = out_dir / "rag-research-questions-20260601-010203.jsonl"
    md_path = out_dir / "rag-research-questions-20260601-010203.md"
    assert jsonl_path.exists()
    assert md_path.exists()
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert rows[0]["question_id"] == "research_q_001"
    assert rows[0]["db_only"] is True
    assert {"question", "topic", "generated_from", "source_refs", "status"} <= set(rows[0])
    assert "# RAG DB-only Research Question Candidates" in md_path.read_text(encoding="utf-8")


def test_generator_fails_without_internal_material(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--chunks-path",
            str(tmp_path / "missing_chunks.jsonl"),
            "--eval-path",
            str(tmp_path / "missing_eval.jsonl"),
            "--out-dir",
            str(tmp_path / "reports"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "no internal RAG material" in result.stdout
