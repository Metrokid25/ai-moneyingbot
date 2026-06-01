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
    assert questions[0]["question"] == "\uae08\ub9ac \uc0c1\uc2b9\uc740 \uc8fc\uc2dd\uc2dc\uc7a5\uc5d0 \uc5b4\ub5a4 \ubd80\ub2f4\uc73c\ub85c \uc791\uc6a9\ud558\ub294\uac00?"
    assert questions[0]["topic"] == "\uae08\ub9ac/\uae34\ucd95/\uc8fc\uc2dd\uc2dc\uc7a5"
    assert all("What investment context" not in question["question"] for question in questions)


def test_generation_result_filters_mojibake_topics_and_reports_skips():
    generator = load_generator()
    eval_path = Path("internal_eval.jsonl")
    eval_rows = [
        {
            "id": "eval-001",
            "question": "\uae08\ub9ac \uc0c1\uc2b9\uc740 \uc8fc\uc2dd\uc2dc\uc7a5\uc5d0 \uc5b4\ub5a4 \uc601\ud5a5\uc744 \uc8fc\ub294\uac00?",
            "category": "rates",
            "expected_topics": ["\u6e72\ub358\u2501", "rates"],
            "expected_keywords": ["\uae08\ub9ac", "discount rates"],
        },
        {
            "id": "eval-002",
            "question": "\ud658\uc728 \uae09\ub4f1\uc740 \uc678\uad6d\uc778 \uc218\uae09\uc5d0 \uc5b4\ub5a4 \uc601\ud5a5\uc744 \uc8fc\ub294\uac00?",
            "category": "fx",
            "expected_topics": ["?\uc12c\uac09\ud23c"],
            "expected_keywords": ["stronger dollar", "foreign flows"],
        },
    ]

    result = generator.build_generation_result({}, {eval_path: eval_rows}, 10)

    assert len(result.questions) == 2
    assert [question["topic"] for question in result.questions] == [
        "\uae08\ub9ac/\uae34\ucd95/\uc8fc\uc2dd\uc2dc\uc7a5",
        "\ud658\uc728/\uc678\uad6d\uc778 \uc218\uae09/\ud55c\uad6d \uc99d\uc2dc",
    ]
    assert result.skipped_topics
    assert all("?" not in question["topic"] for question in result.questions)
    assert all("\u6e72" not in question["question"] for question in result.questions)


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
    assert rows[0]["question"].startswith("\uae08\ub9ac \uc0c1\uc2b9")
    assert "What investment context" not in rows[0]["question"]
    markdown = md_path.read_text(encoding="utf-8")
    assert "# RAG DB-only Research Question Candidates" in markdown
    assert "## Filtered Topics" in markdown
    assert "## Source Counts" in markdown


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
