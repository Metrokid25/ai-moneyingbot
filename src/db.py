import sqlite3
from models import Article
from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                article_id   TEXT PRIMARY KEY,
                title        TEXT,
                url          TEXT NOT NULL,
                author       TEXT,
                posted_at    TEXT,
                raw_html     TEXT,
                clean_text   TEXT,
                source_page  INTEGER,
                status       TEXT NOT NULL DEFAULT 'OK',
                error_reason TEXT,
                saved_at     TEXT NOT NULL
            )
        """)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "author" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN author TEXT")
    if "source_page" not in existing:
        conn.execute("ALTER TABLE articles ADD COLUMN source_page INTEGER")


def article_exists(article_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM articles WHERE article_id = ?", (article_id,)
        ).fetchone()
        return row is not None


def upsert_article(article: Article) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO articles
                (article_id, title, url, author, posted_at, raw_html, clean_text,
                 source_page, status, error_reason, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                title        = excluded.title,
                url          = excluded.url,
                author       = excluded.author,
                posted_at    = excluded.posted_at,
                raw_html     = excluded.raw_html,
                clean_text   = excluded.clean_text,
                source_page  = excluded.source_page,
                status       = excluded.status,
                error_reason = excluded.error_reason,
                saved_at     = excluded.saved_at
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
        ))


def count_indexed() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE status = 'INDEXED'"
        ).fetchone()
        return row[0]
