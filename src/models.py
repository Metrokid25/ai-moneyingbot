from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class Status:
    INDEXED        = "INDEXED"
    BODY_COLLECTED = "BODY_COLLECTED"
    BODY_EMPTY     = "BODY_EMPTY"
    BODY_FAILED    = "BODY_FAILED"
    BODY_BLOCKED   = "BODY_BLOCKED"
    # OK / FAILED: deprecated — main.py one-shot 잔재, Phase 2 신규 코드에서 사용 안 함


@dataclass
class Article:
    article_id: str
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    posted_at: Optional[str] = None
    raw_html: Optional[str] = None
    clean_text: Optional[str] = None
    source_page: Optional[int] = None
    status: str = "OK"
    error_reason: Optional[str] = None
    saved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: Optional[str] = None
