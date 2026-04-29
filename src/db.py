import sqlite3
from datetime import datetime, timezone
from typing import Any, List, Optional

from config import DB_PATH
from models import Article


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                article_id        INTEGER PRIMARY KEY,
                title             TEXT,
                url               TEXT NOT NULL,
                author            TEXT,
                posted_at         TEXT,
                raw_html          TEXT,
                clean_text        TEXT,
                source_page       INTEGER,
                status            TEXT NOT NULL DEFAULT 'OK',
                error_reason      TEXT,
                saved_at          TEXT NOT NULL,
                updated_at        TEXT,
                attempt_count     INTEGER NOT NULL DEFAULT 0,
                last_error_reason TEXT,
                last_attempt_at   TEXT
            )
        """)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "author" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN author TEXT")
    if "source_page" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN source_page INTEGER")
    if "updated_at" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN updated_at TEXT")
        conn.execute("UPDATE articles SET updated_at = saved_at WHERE updated_at IS NULL")
    if "attempt_count" not in existing:
        conn.execute(
            "ALTER TABLE articles ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"
        )
    if "last_error_reason" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN last_error_reason TEXT")
    if "last_attempt_at" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN last_attempt_at TEXT")


def article_exists(article_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM articles WHERE article_id = ?", (article_id,)
        ).fetchone()
        return row is not None


def upsert_article(article: Article) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO articles
                (article_id, title, url, author, posted_at, raw_html, clean_text,
                 source_page, status, error_reason, saved_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                title        = excluded.title,
                url          = excluded.url,
                author       = excluded.author,
                posted_at    = excluded.posted_at,
                raw_html     = excluded.raw_html,
                clean_text   = excluded.clean_text,
                source_page  = excluded.source_page,
                status       = CASE
                    WHEN articles.status IN ('BODY_COLLECTED', 'BODY_BLOCKED')
                        THEN articles.status
                    ELSE excluded.status
                END,
                error_reason = excluded.error_reason,
                updated_at   = excluded.updated_at
        """, (
            article.article_id,
            article.title,
            article.url,
            article.author,
            article.posted_at,
            article.raw_html,
            article.clean_text,
            article.source_page,
            article.status,
            article.error_reason,
            article.saved_at,
            now,
        ))


def get_article_by_id(article_id: int) -> Optional[Article]:
    """단건 조회. 없으면 None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT article_id, title, url, author, posted_at, raw_html, clean_text, "
            "source_page, status, error_reason, saved_at, updated_at "
            "FROM articles WHERE article_id = ?",
            (article_id,),
        ).fetchone()
        if row is None:
            return None
        return Article(
            article_id=row[0],
            title=row[1],
            url=row[2],
            author=row[3],
            posted_at=row[4],
            raw_html=row[5],
            clean_text=row[6],
            source_page=row[7],
            status=row[8],
            error_reason=row[9],
            saved_at=row[10],
            updated_at=row[11],
        )


def get_articles_by_status(status: str, limit: Optional[int] = None) -> List[Article]:
    """status 일치 글 목록. limit=None 이면 전체."""
    sql = (
        "SELECT article_id, title, url, author, posted_at, raw_html, clean_text, "
        "source_page, status, error_reason, saved_at, updated_at "
        "FROM articles WHERE status = ? ORDER BY article_id"
    )
    params: list[Any] = [status]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        Article(
            article_id=row[0],
            title=row[1],
            url=row[2],
            author=row[3],
            posted_at=row[4],
            raw_html=row[5],
            clean_text=row[6],
            source_page=row[7],
            status=row[8],
            error_reason=row[9],
            saved_at=row[10],
            updated_at=row[11],
        )
        for row in rows
    ]


def update_article_body(
    article_id: int,
    raw_html: str,
    clean_text: str,
    new_status: str,
    error_reason: Optional[str] = None,
) -> None:
    """본문/상태만 갱신. BODY_COLLECTED/BODY_BLOCKED 상태 역주행 차단."""
    current = get_article_by_id(article_id)
    if current is None:
        raise ValueError(f"article_id not found: {article_id}")
    if (
        current.status in ("BODY_COLLECTED", "BODY_BLOCKED")
        and new_status != current.status
    ):
        raise ValueError(
            f"status 역주행 차단: {current.status} -> {new_status} "
            f"(article_id={article_id})"
        )
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE articles SET raw_html=?, clean_text=?, status=?, "
            "error_reason=?, updated_at=? WHERE article_id=?",
            (raw_html, clean_text, new_status, error_reason, now, article_id),
        )


def count_indexed() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE status = 'INDEXED'"
        ).fetchone()
        return row[0]
