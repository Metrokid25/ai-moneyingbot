import re
from typing import Any


SOURCE = "naver_cafe_119investment_goodmorning"
REQUIRED_METADATA_FIELDS = {
    "article_id",
    "source_id",
    "source_path",
    "chunk_id",
    "chunk_index",
    "posted_at",
    "created_at",
    "collected_at",
    "year",
    "month",
    "title",
    "body_len",
    "author",
    "source",
    "url",
    "source_url",
    "content_hash",
    "status",
}
REQUIRED_METADATA_TYPES = {
    "article_id": int,
    "source_id": str,
    "source_path": str,
    "chunk_id": str,
    "chunk_index": int,
    "posted_at": str,
    "created_at": str,
    "collected_at": str,
    "year": (int, type(None)),
    "month": (int, type(None)),
    "title": str,
    "body_len": int,
    "author": str,
    "source": str,
    "url": str,
    "source_url": str,
    "content_hash": str,
    "status": str,
}
NULLABLE_METADATA_FIELDS = {"year", "month"}

_DATE_RE = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})\.$")
# 2026-07-02: member_api 경로는 posted_at을 'YYYY-MM-DD HH:MM:SS'로 저장 → ISO 형식도 파싱
_DATE_RE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$")


def build_embedding_text(title: str | None, clean_text: str | None) -> str:
    title_text = title or ""
    body_text = clean_text or ""
    return f"{title_text}\n\n{body_text}".strip()


def parse_year_month(posted_at: str | None) -> tuple[int | None, int | None]:
    if not posted_at:
        return None, None

    stripped = posted_at.strip()
    match = _DATE_RE.match(stripped) or _DATE_RE_ISO.match(stripped)
    if not match:
        return None, None

    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None, None
    return year, month


def split_text_into_chunks(
    embedding_text: str,
    threshold: int = 1500,
    chunk_size: int = 1100,
    overlap: int = 180,
) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = embedding_text.strip()
    if len(text) < threshold:
        return [text]

    paragraph_chunks = _split_by_paragraphs(text, chunk_size)
    if paragraph_chunks is not None:
        return paragraph_chunks

    return _sliding_split(text, chunk_size, overlap)


def build_chunk_records(
    article: dict[str, Any],
    threshold: int = 1500,
    chunk_size: int = 1100,
    overlap: int = 180,
) -> list[dict[str, Any]]:
    article_id = int(article["article_id"])
    title = article.get("title") or ""
    clean_text = article.get("clean_text") or ""
    posted_at = article.get("posted_at")
    created_at = article.get("created_at")
    collected_at = article.get("collected_at")
    author = article.get("author")
    source = article.get("source") or SOURCE
    url = article.get("url")
    source_url = article.get("source_url") or url
    source_id = str(article.get("source_id") or article_id)
    source_path = article.get("source_path") or source_url
    content_hash = article.get("content_hash")
    status = article.get("status") or ""

    embedding_text = build_embedding_text(title, clean_text)
    chunks = split_text_into_chunks(
        embedding_text,
        threshold=threshold,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    year, month = parse_year_month(posted_at)
    body_len = len(clean_text)

    records: list[dict[str, Any]] = []
    for chunk_index, chunk_text in enumerate(chunks):
        chunk_id = f"{article_id}:{chunk_index}"
        metadata = {
            "article_id": article_id,
            "source_id": source_id,
            "source_path": source_path,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "posted_at": posted_at,
            "created_at": created_at,
            "collected_at": collected_at,
            "year": year,
            "month": month,
            "title": title,
            "body_len": body_len,
            "author": author,
            "source": source,
            "url": url,
            "source_url": source_url,
            "content_hash": content_hash,
            "status": status,
        }
        validate_chunk_metadata(metadata, chunk_id=chunk_id)
        records.append(
            {
                "chunk_id": chunk_id,
                "article_id": article_id,
                "chunk_index": chunk_index,
                "embedding_text": chunk_text,
                "metadata": metadata,
            }
        )
    return records


def validate_chunk_metadata(metadata: dict[str, Any], chunk_id: str | None = None) -> None:
    missing = sorted(REQUIRED_METADATA_FIELDS - set(metadata))
    label = f"chunk {chunk_id}" if chunk_id is not None else "chunk metadata"
    if missing:
        raise ValueError(f"{label} metadata missing required fields: {', '.join(missing)}")

    empty = [
        field
        for field in sorted(REQUIRED_METADATA_FIELDS - NULLABLE_METADATA_FIELDS)
        if metadata.get(field) is None
        or (isinstance(metadata.get(field), str) and not metadata[field].strip())
    ]
    if empty:
        raise ValueError(f"{label} metadata empty required fields: {', '.join(empty)}")

    type_mismatches = [
        f"{field} expected {_type_name(expected_type)}, got {type(metadata[field]).__name__}"
        for field, expected_type in sorted(REQUIRED_METADATA_TYPES.items())
        if field in metadata and not isinstance(metadata[field], expected_type)
    ]
    if type_mismatches:
        raise ValueError(f"{label} metadata type mismatches: {', '.join(type_mismatches)}")

    if chunk_id is not None and metadata.get("chunk_id") != chunk_id:
        raise ValueError(f"chunk {chunk_id} metadata chunk_id mismatch")

    article_id = metadata.get("article_id")
    chunk_index = metadata.get("chunk_index")
    if isinstance(article_id, int) and isinstance(chunk_index, int):
        expected_chunk_id = f"{article_id}:{chunk_index}"
        if metadata.get("chunk_id") != expected_chunk_id:
            raise ValueError(
                f"{label} metadata chunk_id must be {expected_chunk_id}, got {metadata.get('chunk_id')}"
            )


def _type_name(expected_type: type | tuple[type, ...]) -> str:
    if isinstance(expected_type, tuple):
        return " or ".join(t.__name__ for t in expected_type)
    return expected_type.__name__


def _split_by_paragraphs(text: str, chunk_size: int) -> list[str] | None:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paragraphs) <= 1:
        return None
    if any(len(p) > chunk_size for p in paragraphs):
        return None

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        separator_len = 2 if current else 0
        if current and current_len + separator_len + paragraph_len > chunk_size:
            chunks.append("\n\n".join(current).strip())
            current = [paragraph]
            current_len = paragraph_len
        else:
            current.append(paragraph)
            current_len += separator_len + paragraph_len

    if current:
        chunks.append("\n\n".join(current).strip())

    if len(chunks) <= 1:
        return None
    return [chunk for chunk in chunks if chunk]


def _sliding_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    stride = chunk_size - overlap
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == text_len:
            break
        start += stride

    return chunks
