from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, NamedTuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHUNKS_PATHS = (
    PROJECT_ROOT / "data" / "chunks_phase2.jsonl",
    PROJECT_ROOT / "tests" / "fixtures" / "sample_articles.jsonl",
)
DEFAULT_EVAL_PATHS = (
    PROJECT_ROOT / "tests" / "fixtures" / "rag_eval_questions.jsonl",
    PROJECT_ROOT / "tests" / "fixtures" / "rag_golden_questions.jsonl",
)
DEFAULT_OUT_DIR = PROJECT_ROOT / "agent_reports"

TOKEN_RE = re.compile(r"[A-Za-z0-9_\-./%+]+|[\uac00-\ud7a3]{2,}")
STOPWORDS = {
    "a",
    "and",
    "are",
    "article",
    "because",
    "body",
    "can",
    "chunk",
    "duplicate",
    "for",
    "from",
    "how",
    "into",
    "market",
    "markets",
    "question",
    "retrieval",
    "should",
    "source",
    "stock",
    "stocks",
    "test",
    "that",
    "the",
    "this",
    "through",
    "what",
    "when",
    "where",
    "why",
    "with",
}


class TopicEvidence(NamedTuple):
    topic: str
    source_ref: str
    generated_from: str
    preview: str


class TopicRule(NamedTuple):
    topic: str
    question: str
    aliases: tuple[str, ...]


class GenerationResult(NamedTuple):
    questions: list[dict[str, Any]]
    skipped_topics: dict[str, int]
    source_counts: dict[str, int]


TOPIC_RULES: tuple[TopicRule, ...] = (
    TopicRule(
        "\uae08\ub9ac/\uae34\ucd95/\uc8fc\uc2dd\uc2dc\uc7a5",
        "\uae08\ub9ac \uc0c1\uc2b9\uc740 \uc8fc\uc2dd\uc2dc\uc7a5\uc5d0 \uc5b4\ub5a4 \ubd80\ub2f4\uc73c\ub85c \uc791\uc6a9\ud558\ub294\uac00?",
        ("rates", "higher rates", "discount rates", "\uae08\ub9ac", "\ucc44\uad8c\uae08\ub9ac", "\uae34\ucd95"),
    ),
    TopicRule(
        "\ud658\uc728/\uc678\uad6d\uc778 \uc218\uae09/\ud55c\uad6d \uc99d\uc2dc",
        "\ud658\uc728 \uae09\ub4f1\uc740 \ud55c\uad6d \uc8fc\uc2dd\uc2dc\uc7a5\uacfc \uc678\uad6d\uc778 \uc218\uae09\uc5d0 \uc5b4\ub5a4 \uc601\ud5a5\uc744 \uc8fc\ub294\uac00?",
        ("fx", "stronger dollar", "foreign flows", "korean equities", "\ud658\uc728", "\ub2ec\ub7ec", "\uc678\uad6d\uc778", "\uc218\uae09"),
    ),
    TopicRule(
        "\uacbd\uae30\uce68\uccb4/\uc2dc\uc7a5 \uc2e0\ud638",
        "\uacbd\uae30\uce68\uccb4 \uad6d\uba74\uc5d0\uc11c \uc8fc\uc2dd\uc2dc\uc7a5\uc740 \uc5b4\ub5a4 \uc2e0\ud638\ub97c \uba3c\uc800 \ubc18\uc601\ud558\ub294\uac00?",
        ("cycle", "recession", "\uacbd\uae30", "\uce68\uccb4", "\ubc29\uc5b4", "\uc0ac\uc774\ud074"),
    ),
    TopicRule(
        "\uc720\ub3d9\uc131/\uae34\ucd95 \uc7a5\uc138",
        "\uc720\ub3d9\uc131 \uc7a5\uc138\uc640 \uae34\ucd95 \uc7a5\uc138\ub294 \uc5b4\ub5bb\uac8c \ub2e4\ub974\uac8c \ud574\uc11d\ud574\uc57c \ud558\ub294\uac00?",
        ("liquidity", "tightening", "\uc720\ub3d9\uc131", "\uae34\ucd95", "\ud1b5\ud654"),
    ),
    TopicRule(
        "\ubd80\ub3d9\uc0b0/\uc804\uc138\uac00\uc728/\ub300\ucd9c",
        "\ubd80\ub3d9\uc0b0 \ud558\ub77d\uc7a5\uc5d0\uc11c \uc804\uc138\uac00\uc728\uc740 \uc65c \uc911\uc694\ud55c\uac00?",
        ("real_estate", "real estate", "\ubd80\ub3d9\uc0b0", "\uc804\uc138\uac00\uc728", "\ub300\ucd9c"),
    ),
    TopicRule(
        "\ubc18\ub3c4\uccb4/\uc0ac\uc774\ud074/\uc218\uae09",
        "\ubc18\ub3c4\uccb4 \uc0ac\uc774\ud074\uc740 \uc5b4\ub5a4 \ubc29\uc2dd\uc73c\ub85c \ud310\ub2e8\ud574\uc57c \ud558\ub294\uac00?",
        ("semiconductor", "\ubc18\ub3c4\uccb4", "\uc5c5\ud669", "\uc0bc\uc131\uc804\uc790", "\uc218\uae09"),
    ),
    TopicRule(
        "\uae08/\uc548\uc804\uc790\uc0b0/\uac70\uc2dc\ud658\uacbd",
        "\uae08\uc740 \uc5b4\ub5a4 \uac70\uc2dc\uacbd\uc81c \ud658\uacbd\uc5d0\uc11c \ubc29\uc5b4 \uc790\uc0b0\uc73c\ub85c \ud574\uc11d\ub418\ub294\uac00?",
        ("gold", "\uc548\uc804\uc790\uc0b0", "\uc778\ud50c\ub808\uc774\uc158"),
    ),
    TopicRule(
        "\uac70\ub798\ub7c9/\ucc28\ud2b8/\uc704\ud5d8 \uc2e0\ud638",
        "\uac70\ub798\ub7c9 \uc99d\uac00\ub294 \uc5b8\uc81c \uae0d\uc815 \uc2e0\ud638\uc774\uace0 \uc5b8\uc81c \uc704\ud5d8 \uc2e0\ud638\uc778\uac00?",
        ("volume", "chart", "\uac70\ub798\ub7c9", "\ucc28\ud2b8", "\uacfc\uc5f4"),
    ),
    TopicRule(
        "\ub9ac\uc2a4\ud06c/\uc190\uc808/\uc775\uc808",
        "\uc190\uc808 \uae30\uc900\uc740 \uc5b4\ub5a4 \uc0c1\ud669\uc5d0\uc11c \ud544\uc694\ud558\ub2e4\uace0 \uc124\uba85\ub418\ub294\uac00?",
        ("risk", "stop loss", "take profit", "\ub9ac\uc2a4\ud06c", "\uc190\uc808", "\uc775\uc808", "\uacfc\uc5f4"),
    ),
    TopicRule(
        "\ud14c\ub9c8\uc8fc/\ub9e4\ub9e4/\uc218\uae09",
        "\ud14c\ub9c8\uc8fc \ub9e4\ub9e4\uc5d0\uc11c \uac00\uc7a5 \uacbd\uacc4\ud574\uc57c \ud560 \uc870\uac74\uc740 \ubb34\uc5c7\uc778\uac00?",
        ("theme", "\ud14c\ub9c8", "\ud14c\ub9c8\uc8fc", "\ub9e4\ub9e4", "\uc218\uae09"),
    ),
    TopicRule(
        "\uc815\ucc45/\uaddc\uc81c/\uc5c5\uc885",
        "\uc815\ucc45\uc774\ub098 \uaddc\uc81c \ubcc0\ud654\ub294 \uc5c5\uc885 \ud22c\uc790 \ud310\ub2e8\uc5d0 \uc5b4\ub5bb\uac8c \ubc18\uc601\ud574\uc57c \ud558\ub294\uac00?",
        ("policy", "regulation", "\uc815\ucc45", "\uaddc\uc81c", "\uc5c5\uc885"),
    ),
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
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


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_match_text(value: Any) -> str:
    return normalize_space(value).casefold().replace("_", " ")


def has_mojibake(value: str) -> bool:
    stripped = value.strip()
    if "\ufffd" in stripped:
        return True
    if "?" in stripped.rstrip("? "):
        return True
    return any("\u4e00" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff" for char in stripped)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text):
        token = match.group(0).strip("_./%-").casefold()
        if len(token) < 2 or token in STOPWORDS or token.isdigit():
            continue
        tokens.append(token)
    return tokens


def preview_text(text: str, limit: int = 160) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def source_ref_from_chunk(chunk: dict[str, Any], source_name: str | None = None) -> str:
    metadata = chunk.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    article_id = chunk.get("article_id") or metadata.get("article_id") or "unknown"
    chunk_id = chunk.get("chunk_id") or metadata.get("chunk_id")
    prefix = f"{source_name}:" if source_name else ""
    if chunk_id:
        return f"{prefix}article_id:{article_id}:chunk_id:{chunk_id}"
    return f"{prefix}article_id:{article_id}"


def topic_evidence_from_chunks(
    chunks: Iterable[dict[str, Any]],
    source_name: str | None = None,
) -> list[TopicEvidence]:
    evidence: list[TopicEvidence] = []
    for chunk in chunks:
        metadata = chunk.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        title = normalize_space(metadata.get("title") or chunk.get("title"))
        text = normalize_space(
            chunk.get("embedding_text")
            or chunk.get("text")
            or chunk.get("chunk_text")
            or chunk.get("body_text")
            or chunk.get("clean_text")
        )
        source_ref = source_ref_from_chunk(chunk, source_name)

        for token in dict.fromkeys(tokenize(title)):
            evidence.append(TopicEvidence(token, source_ref, "title", title))
        for token in list(dict.fromkeys(tokenize(text)))[:16]:
            evidence.append(TopicEvidence(token, source_ref, "chunk_keyword", preview_text(text)))
    return evidence


def topic_evidence_from_eval(rows: Iterable[dict[str, Any]], path: Path) -> list[TopicEvidence]:
    evidence: list[TopicEvidence] = []
    for row in rows:
        row_id = normalize_space(row.get("id")) or "unknown"
        source_ref = f"{path.name}:{row_id}"
        question = normalize_space(row.get("question"))
        topics = row.get("expected_topics")
        keywords = row.get("expected_keywords")
        sources = row.get("expected_sources")
        if not isinstance(topics, list):
            topics = []
        if not isinstance(keywords, list):
            keywords = []
        if not isinstance(sources, list):
            sources = []

        category = normalize_space(row.get("category"))
        terms = [category, *[normalize_space(v) for v in topics], *[normalize_space(v) for v in keywords]]
        for term in terms:
            if term:
                evidence.append(TopicEvidence(term.casefold(), source_ref, "existing_eval", question))
        for source in sources:
            if not isinstance(source, dict):
                continue
            title = normalize_space(source.get("title"))
            article_id = normalize_space(source.get("article_id"))
            chunk_id = normalize_space(source.get("chunk_id"))
            ref = f"article_id:{article_id}:chunk_id:{chunk_id}" if chunk_id else source_ref
            for token in dict.fromkeys(tokenize(title)):
                evidence.append(TopicEvidence(token, ref, "source_metadata", title))
    return evidence


def group_evidence(evidence: Iterable[TopicEvidence]) -> dict[str, list[TopicEvidence]]:
    grouped: dict[str, list[TopicEvidence]] = defaultdict(list)
    for item in evidence:
        topic = normalize_space(item.topic)
        if not topic:
            continue
        refs = {(existing.source_ref, existing.generated_from) for existing in grouped[topic]}
        if (item.source_ref, item.generated_from) not in refs:
            grouped[topic].append(item)
    return dict(grouped)


def evidence_matches_rule(topic: str, rule: TopicRule) -> bool:
    normalized_topic = normalize_match_text(topic)
    return any(alias in normalized_topic for alias in rule.aliases)


def build_question(
    index: int,
    rule: TopicRule,
    evidence_items: list[TopicEvidence],
) -> dict[str, Any]:
    generated_from = sorted({item.generated_from for item in evidence_items})
    source_refs = list(dict.fromkeys(item.source_ref for item in evidence_items))[:6]
    previews = [
        item.preview
        for item in evidence_items
        if item.preview and not has_mojibake(item.preview)
    ][:3]

    return {
        "question_id": f"research_q_{index:03d}",
        "question": rule.question,
        "topic": rule.topic,
        "generated_from": generated_from,
        "source_refs": source_refs,
        "db_only": True,
        "status": "candidate",
        "evidence_previews": previews,
    }


def build_generation_result(
    chunks_by_path: dict[Path, list[dict[str, Any]]],
    eval_rows_by_path: dict[Path, list[dict[str, Any]]],
    max_questions: int,
) -> GenerationResult:
    if max_questions < 1:
        raise ValueError("max_questions must be positive")

    evidence: list[TopicEvidence] = []
    source_counts: Counter[str] = Counter()
    for path, chunks in chunks_by_path.items():
        evidence.extend(topic_evidence_from_chunks(chunks, path.name))
        source_counts[str(path)] += len(chunks)
    for path, rows in eval_rows_by_path.items():
        evidence.extend(topic_evidence_from_eval(rows, path))
        source_counts[str(path)] += len(rows)

    grouped = group_evidence(evidence)
    skipped_topics: Counter[str] = Counter()
    valid_grouped: dict[str, list[TopicEvidence]] = {}
    for topic, items in grouped.items():
        if has_mojibake(topic):
            skipped_topics[topic] += len(items)
            continue
        valid_grouped[topic] = items

    questions: list[dict[str, Any]] = []
    for rule in TOPIC_RULES:
        matched: list[TopicEvidence] = []
        for topic, items in valid_grouped.items():
            if evidence_matches_rule(topic, rule):
                matched.extend(items)
        if not matched:
            continue
        matched.sort(key=lambda item: (item.source_ref, item.generated_from, item.topic))
        questions.append(build_question(len(questions) + 1, rule, matched))
        if len(questions) >= max_questions:
            break

    return GenerationResult(
        questions,
        dict(sorted(skipped_topics.items())),
        dict(sorted(source_counts.items())),
    )


def build_research_questions(
    chunks: list[dict[str, Any]],
    eval_rows_by_path: dict[Path, list[dict[str, Any]]],
    max_questions: int,
) -> list[dict[str, Any]]:
    result = build_generation_result({Path("<chunks>"): chunks}, eval_rows_by_path, max_questions)
    return result.questions


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def format_markdown_report(
    result: GenerationResult,
    chunks_paths: list[Path],
    eval_paths: list[Path],
    generated_at: str,
) -> str:
    lines = [
        "# RAG DB-only Research Question Candidates",
        "",
        f"- generated_at: {generated_at}",
        "- db_only: true",
        f"- question_count: {len(result.questions)}",
        "- chunks_or_article_paths:",
    ]
    lines.extend(f"  - {path}" for path in chunks_paths)
    lines.append("- eval_paths:")
    lines.extend(f"  - {path}" for path in eval_paths)
    lines.extend(["", "## Source Counts", ""])
    for path, count in result.source_counts.items():
        lines.append(f"- {path}: {count}")

    lines.extend(["", "## Filtered Topics", ""])
    if not result.skipped_topics:
        lines.append("- none")
    else:
        for topic, count in result.skipped_topics.items():
            lines.append(f"- {topic}: {count}")

    lines.extend(["", "## Candidates", ""])
    for question in result.questions:
        lines.extend(
            [
                f"### {question['question_id']}",
                "",
                f"- question: {question['question']}",
                f"- topic: {question['topic']}",
                f"- generated_from: {', '.join(question['generated_from'])}",
                f"- source_refs: {', '.join(question['source_refs'])}",
                f"- status: {question['status']}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def existing_paths(paths: Iterable[Path]) -> list[Path]:
    return [path for path in paths if path.exists()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate DB-only RAG research question candidates from internal artifacts.",
    )
    parser.add_argument(
        "--chunks-path",
        type=Path,
        action="append",
        dest="chunks_paths",
        default=None,
        help="Internal chunk/article JSONL. Can be passed more than once.",
    )
    parser.add_argument(
        "--eval-path",
        type=Path,
        action="append",
        dest="eval_paths",
        default=None,
        help="Internal evaluation/golden question JSONL. Can be passed more than once.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-questions", type=int, default=20)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    chunks_paths = existing_paths(args.chunks_paths or DEFAULT_CHUNKS_PATHS)
    eval_paths = existing_paths(args.eval_paths or DEFAULT_EVAL_PATHS)

    try:
        chunks_by_path = {path: read_jsonl(path) for path in chunks_paths}
        eval_rows_by_path = {path: read_jsonl(path) for path in eval_paths}
        result = build_generation_result(chunks_by_path, eval_rows_by_path, args.max_questions)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 1

    if not result.questions:
        print("error: no internal RAG material found for quality question generation")
        return 1

    stamp = args.timestamp or timestamp_now()
    jsonl_path = args.out_dir / f"rag-research-questions-{stamp}.jsonl"
    md_path = args.out_dir / f"rag-research-questions-{stamp}.md"
    write_jsonl(jsonl_path, result.questions)
    md_path.write_text(
        format_markdown_report(result, chunks_paths, eval_paths, stamp),
        encoding="utf-8",
        newline="\n",
    )

    print(f"Generated {len(result.questions)} DB-only research questions")
    print(f"Filtered mojibake topics: {len(result.skipped_topics)}")
    print(f"JSONL: {jsonl_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
