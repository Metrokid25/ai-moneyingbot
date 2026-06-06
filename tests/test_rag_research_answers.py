import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "run_rag_research_answers.py"
BAD_ANSWER_PHRASES = (
    "검색 결과 1의 제목은",
    "해당 근거에서는",
    "논리가 반복된다",
    "라는 근거 흐름으로 정리된다",
    "다른 preview에서는",
    "추가 preview에서는",
    "보조 근거로는",
    "근거를 하나 더 붙이면",
    "상위 근거 안에서 참고할 수 있는 내용은",
    "DB preview에서",
    "질문은",
    "살펴보면",
)


def load_runner():
    spec = importlib.util.spec_from_file_location("run_rag_research_answers", SCRIPT)
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


def first_sentence(text: str) -> str:
    return text.split(".", 1)[0]


def assert_no_bad_answer_phrases(answer: str) -> None:
    for phrase in BAD_ANSWER_PHRASES:
        assert phrase not in answer


def retrieval_record(**overrides):
    row = {
        "question_id": "research_q_001",
        "question": "금리 상승은 주식시장에 어떤 부담으로 작용하는가?",
        "topic": "금리/긴축/주식시장",
        "db_only": True,
        "retrieval_status": "ok",
        "backend_status": "ok",
        "top_k": 5,
        "results": [
            {
                "rank": 1,
                "article_id": 75890,
                "chunk_id": "75890:0",
                "title": "긴축은 주식시장의 악재",
                "score": 0.51,
                "source_ref": "article_id:75890:chunk_id:75890:0",
                "text_preview": "금리인상은 긴축을 의미하고 자산가격에는 악재입니다. 주식시장도 금리인상 영향권에 있다고 설명합니다.",
            },
            {
                "rank": 2,
                "article_id": 124102,
                "chunk_id": "124102:1",
                "title": "시장금리 상승과 환차손",
                "score": 0.49,
                "source_ref": "article_id:124102:chunk_id:124102:1",
                "text_preview": "금리 상승은 긴축효과를 가지고 있고 외국인 매수가 제한적이라고 설명합니다.",
            },
        ],
    }
    row.update(overrides)
    return row


def research_q_006_like_record():
    return retrieval_record(
        question_id="research_q_006",
        question="반도체 사이클은 어떤 방식으로 판단해야 하는가?",
        topic="반도체/사이클/수급",
        results=[
            {
                "rank": 1,
                "article_id": 606,
                "chunk_id": "606:0",
                "title": "반도체 기판 단서",
                "score": 0.43,
                "source_ref": "article_id:606:chunk_id:606:0",
                "text_preview": "반도체는 기판을 우선적으로 봐야 한다고 설명합니다.",
            }
        ],
    )


def research_q_007_like_record():
    return retrieval_record(
        question_id="research_q_007",
        question="금은 어떤 거시경제 환경에서 방어 자산으로 해석되는가?",
        topic="금/안전자산/거시환경",
        results=[
            {
                "rank": 1,
                "article_id": 707,
                "chunk_id": "707:0",
                "title": "시장 붕괴 단서",
                "score": 0.44,
                "source_ref": "article_id:707:chunk_id:707:0",
                "text_preview": "시장이 붕괴가 되면 대책은 그래도 필요하다고 설명합니다.",
            },
            {
                "rank": 2,
                "article_id": 708,
                "chunk_id": "708:0",
                "title": "달러 통화가치 단서",
                "score": 0.41,
                "source_ref": "article_id:708:chunk_id:708:0",
                "text_preview": "이 말은 달러 통화가치가 하락압력을 받는다는 뜻입니다.",
            },
        ],
    )


def test_find_latest_retrieval_file_uses_latest_report_timestamp(tmp_path):
    runner = load_runner()
    older = tmp_path / "rag-research-retrieval-20260601-010101.jsonl"
    newer = tmp_path / "rag-research-retrieval-20260601-020202.jsonl"
    write_jsonl(older, [retrieval_record(question_id="research_q_001")])
    write_jsonl(newer, [retrieval_record(question_id="research_q_002")])

    assert runner.find_latest_retrieval_file(tmp_path) == newer


def test_load_retrieval_records_validates_db_only_and_results(tmp_path):
    runner = load_runner()
    path = tmp_path / "retrieval.jsonl"
    write_jsonl(path, [retrieval_record()])

    rows = runner.load_retrieval_records(path)

    assert rows[0]["question_id"] == "research_q_001"
    assert rows[0]["db_only"] is True
    assert len(rows[0]["results"]) == 2

    write_jsonl(path, [retrieval_record(db_only=False)])
    with pytest.raises(ValueError, match="db_only=true"):
        runner.load_retrieval_records(path)


def test_build_answer_record_synthesizes_conclusion_without_repetitive_templates():
    runner = load_runner()

    answer = runner.build_answer_record(retrieval_record())

    assert answer["answer_status"] == "ok"
    assert answer["db_only"] is True
    assert answer["question_id"] == "research_q_001"
    assert answer["answer"].startswith("DB 근거상 핵심은")
    assert "금리 상승은 주식시장에 어떤 부담으로 작용하는가" not in first_sentence(answer["answer"])
    assert "금리/긴축/주식시장" not in answer["answer"]
    assert "금리인상은 긴축을 의미" in answer["answer"]
    assert "주식시장도 금리인상 영향권" in answer["answer"]
    assert_no_bad_answer_phrases(answer["answer"])
    assert "현재" not in answer["answer"]
    assert answer["unsupported_claims"] == []
    assert answer["missing_evidence"] == []
    assert answer["used_sources"] == [
        {
            "rank": 1,
            "article_id": 75890,
            "chunk_id": "75890:0",
            "title": "긴축은 주식시장의 악재",
            "source_ref": "article_id:75890:chunk_id:75890:0",
        },
        {
            "rank": 2,
            "article_id": 124102,
            "chunk_id": "124102:1",
            "title": "시장금리 상승과 환차손",
            "source_ref": "article_id:124102:chunk_id:124102:1",
        },
    ]


def test_build_answer_record_marks_weak_evidence_for_low_score():
    runner = load_runner()
    weak = retrieval_record(
        results=[
            {
                "rank": 1,
                "article_id": 1,
                "chunk_id": "1:0",
                "title": "낮은 점수 근거",
                "score": 0.21,
                "source_ref": "article_id:1:chunk_id:1:0",
                "text_preview": "검색 근거가 하나뿐이고 점수가 낮습니다.",
            }
        ]
    )

    answer = runner.build_answer_record(weak)

    assert answer["answer_status"] == "weak_evidence"
    assert "확정하기 어렵다" in answer["answer"]
    assert "추가 근거 수집이 필요하다" in answer["answer"]
    assert "검색 근거가 하나뿐이고 점수가 낮다 수준이다" in answer["answer"]
    assert_no_bad_answer_phrases(answer["answer"])
    assert answer["missing_evidence"]
    assert len(answer["used_sources"]) == 1


@pytest.mark.parametrize("record_factory", [research_q_006_like_record, research_q_007_like_record])
def test_weak_evidence_research_q_006_and_q_007_style_records_stay_insufficient(record_factory):
    runner = load_runner()

    answer = runner.build_answer_record(record_factory())

    assert answer["answer_status"] == "weak_evidence"
    assert answer["answer"].startswith("검색된 DB preview만으로는")
    assert "확정하기 어렵다" in answer["answer"]
    assert "확인 가능한 단서는" in answer["answer"]
    assert "추가 근거 수집이 필요하다" in answer["answer"]
    assert "DB 근거상 핵심은" not in answer["answer"]
    assert "방어 자산으로 해석된다" not in answer["answer"]
    assert "사이클은 기판으로 판단해야 한다" not in answer["answer"]
    assert_no_bad_answer_phrases(answer["answer"])


def test_build_answer_record_does_not_synthesize_from_title_only():
    runner = load_runner()
    title_only = retrieval_record(
        results=[
            {
                "rank": 1,
                "article_id": 10,
                "chunk_id": "10:0",
                "title": "긴축은 주식시장의 악재",
                "score": 0.62,
                "source_ref": "article_id:10:chunk_id:10:0",
                "text_preview": "",
            },
            {
                "rank": 2,
                "article_id": 20,
                "chunk_id": "20:0",
                "title": "시장금리 상승과 환차손",
                "score": 0.58,
                "source_ref": "article_id:20:chunk_id:20:0",
                "text_preview": "",
            },
        ]
    )

    answer = runner.build_answer_record(title_only)

    assert answer["answer_status"] == "weak_evidence"
    assert "긴축은 주식시장의 악재" not in answer["answer"]
    assert "시장금리 상승과 환차손" not in answer["answer"]
    assert "유효한 text_preview가 충분하지 않다는 것 수준이다" in answer["answer"]
    assert "no usable text_preview evidence" in answer["missing_evidence"]
    assert answer["used_sources"][0]["title"] == "긴축은 주식시장의 악재"
    assert answer["used_sources"][0]["source_ref"] == "article_id:10:chunk_id:10:0"


def test_build_answer_record_filters_current_context_terms_from_answer_text():
    runner = load_runner()
    row = retrieval_record(
        results=[
            {
                "rank": 1,
                "article_id": 10,
                "chunk_id": "10:0",
                "title": "오늘은 금리 이야기",
                "score": 0.5,
                "source_ref": "article_id:10:chunk_id:10:0",
                "text_preview": "현재 금리는 알 수 없습니다. 이번 주 시장은 알 수 없습니다. 금리 상승은 긴축 효과로 설명됩니다.",
            },
            {
                "rank": 2,
                "article_id": 20,
                "chunk_id": "20:0",
                "title": "긴축 효과",
                "score": 0.48,
                "source_ref": "article_id:20:chunk_id:20:0",
                "text_preview": "주식시장은 금리 영향권에 있다고 설명됩니다.",
            },
        ]
    )

    answer = runner.build_answer_record(row)

    assert "오늘" not in answer["answer"]
    assert "현재" not in answer["answer"]
    assert "이번 주" not in answer["answer"]
    assert "금리 상승은 긴축 효과" in answer["answer"]
    assert "긴축 효과" in answer["answer"]


def test_build_answer_record_skips_backend_unavailable():
    runner = load_runner()
    answer = runner.build_answer_record(
        retrieval_record(
            retrieval_status="backend_unavailable",
            backend_status="unavailable",
            results=[],
        )
    )

    assert answer["answer_status"] == "backend_unavailable"
    assert answer["answer"] == ""
    assert answer["used_sources"] == []
    assert answer["missing_evidence"] == ["retrieval backend unavailable"]


def test_build_answer_record_skips_no_results():
    runner = load_runner()
    answer = runner.build_answer_record(
        retrieval_record(
            retrieval_status="no_results",
            results=[],
        )
    )

    assert answer["answer_status"] == "no_evidence"
    assert answer["answer"] == ""
    assert answer["used_sources"] == []
    assert answer["missing_evidence"] == ["no retrieval results"]


def test_write_jsonl_uses_ascii_escapes(tmp_path):
    runner = load_runner()
    path = tmp_path / "answers.jsonl"

    runner.write_jsonl(path, [{"answer": "금리 상승"}])

    raw = path.read_text(encoding="utf-8")
    assert "\\uae08\\ub9ac" in raw
    assert "금리" not in raw


def test_format_markdown_report_is_readable():
    runner = load_runner()
    answer = runner.build_answer_record(retrieval_record())

    markdown = runner.format_markdown_report(
        [answer],
        retrieval_file=Path("agent_reports/retrieval.jsonl"),
        generated_at="20260601-010203",
    )

    assert "# RAG DB-only Research Answer Drafts" in markdown
    assert "- db_only: true" in markdown
    assert "- answer_ok: 1" in markdown
    assert "### research_q_001" in markdown
    assert "| rank | article_id | chunk_id | title | source_ref |" in markdown
    assert "긴축은 주식시장의 악재" in markdown


def test_cli_writes_answer_reports(tmp_path):
    retrieval_path = tmp_path / "retrieval.jsonl"
    out_dir = tmp_path / "reports"
    write_jsonl(retrieval_path, [retrieval_record()])

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--retrieval-file",
            str(retrieval_path),
            "--out-dir",
            str(out_dir),
            "--timestamp",
            "20260601-010203",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    jsonl_path = out_dir / "rag-research-answers-20260601-010203.jsonl"
    md_path = out_dir / "rag-research-answers-20260601-010203.md"
    assert jsonl_path.exists()
    assert md_path.exists()
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["answer_status"] == "ok"
    assert rows[0]["used_sources"]
    assert "# RAG DB-only Research Answer Drafts" in md_path.read_text(encoding="utf-8-sig")


def test_cli_help_runs_without_generation():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Generate DB-only draft answers" in result.stdout
