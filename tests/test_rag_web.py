import http.client
import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import serve_rag_web


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class RunningServer:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, fake_run, archive_db_path: Path):
        monkeypatch.setattr(serve_rag_web, "run_rag_answer", fake_run)
        self.server = serve_rag_web.RagHTTPServer(
            ("127.0.0.1", 0),
            serve_rag_web.RagWebHandler,
            qdrant_path=serve_rag_web.DEFAULT_QDRANT_PATH,
            archive_db_path=archive_db_path,
            collection=serve_rag_web.DEFAULT_COLLECTION,
            project_root=serve_rag_web.PROJECT_ROOT,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def request(self, method: str, path: str, body: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, response.getheaders(), data


def create_archive_db(path: Path, rows: list[dict] | None = None) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE articles (
                article_id INTEGER PRIMARY KEY,
                title TEXT,
                url TEXT NOT NULL,
                author TEXT,
                posted_at TEXT,
                raw_html TEXT,
                clean_text TEXT,
                source_page INTEGER,
                status TEXT NOT NULL,
                error_reason TEXT,
                saved_at TEXT NOT NULL,
                updated_at TEXT,
                attempt_count INTEGER NOT NULL,
                last_error_reason TEXT,
                last_attempt_at TEXT
            )
            """
        )
        for row in rows or []:
            conn.execute(
                """
                INSERT INTO articles (
                    article_id, title, url, author, posted_at, raw_html, clean_text,
                    source_page, status, error_reason, saved_at, updated_at,
                    attempt_count, last_error_reason, last_attempt_at
                ) VALUES (
                    :article_id, :title, :url, :author, :posted_at, :raw_html, :clean_text,
                    :source_page, :status, :error_reason, :saved_at, :updated_at,
                    :attempt_count, :last_error_reason, :last_attempt_at
                )
                """,
                {
                    "article_id": row["article_id"],
                    "title": row.get("title"),
                    "url": row.get("url", "https://cafe.naver.com/example"),
                    "author": row.get("author"),
                    "posted_at": row.get("posted_at"),
                    "raw_html": row.get("raw_html"),
                    "clean_text": row.get("clean_text"),
                    "source_page": row.get("source_page"),
                    "status": row.get("status", "BODY_COLLECTED"),
                    "error_reason": row.get("error_reason"),
                    "saved_at": row.get("saved_at", "2026-05-01T00:00:00+00:00"),
                    "updated_at": row.get("updated_at"),
                    "attempt_count": row.get("attempt_count", 1),
                    "last_error_reason": row.get("last_error_reason"),
                    "last_attempt_at": row.get("last_attempt_at"),
                },
            )
        conn.commit()
    finally:
        conn.close()
    return path


def sample_article(**overrides):
    row = {
        "article_id": 10,
        "title": "sample title",
        "url": "https://cafe.naver.com/ArticleRead.nhn?clubid=1&articleid=10",
        "author": "author name",
        "posted_at": "2024.01.02.",
        "raw_html": "<p>raw body</p>",
        "clean_text": "clean body text",
    }
    row.update(overrides)
    return row


@pytest.fixture
def archive_db_path(tmp_path):
    return create_archive_db(tmp_path / "archive.db", [sample_article()])


def test_get_root_returns_html(monkeypatch, archive_db_path):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for GET /")

    with RunningServer(monkeypatch, fake_run, archive_db_path) as server:
        status, headers, body = server.request("GET", "/")

    html = body.decode("utf-8")
    assert status == 200
    assert "text/html" in dict(headers)["Content-Type"]
    assert "질문" in html
    assert "실행" in html
    assert "실행 시 Voyage/OpenAI API 호출 및 비용이 발생할 수 있음" in html


def test_post_answer_returns_mocked_result_and_expected_arguments(monkeypatch, archive_db_path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "query": kwargs["query"],
            "answer": "mock answer",
            "sources": [
                {
                    "chunk_id": "10:0",
                    "article_id": 10,
                    "url": "https://example.test/exported/10",
                    "source_url": "https://example.test/exported/10",
                    "created_at": "2026.05.18.",
                    "collected_at": "2026-05-18T09:00:00+09:00",
                    "source": "sample_archive_export",
                    "title": "sample title",
                    "score": 0.91,
                }
            ],
            "model": kwargs["model"],
            "top_k": kwargs["top_k"],
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            "estimated_cost": {"model": kwargs["model"], "total_usd": 0.000003},
        }

    with RunningServer(monkeypatch, fake_run, archive_db_path) as server:
        status, headers, body = server.request(
            "POST",
            "/api/answer",
            {
                "query": "rate question",
                "top_k": "3",
                "model": "gpt-4o-mini",
                "embedding_model": "voyage-3-large",
            },
        )

    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert "application/json" in dict(headers)["Content-Type"]
    assert payload == {
        "ok": True,
        "answer": "mock answer",
        "sources": [
            {
                "chunk_id": "10:0",
                "article_id": 10,
                "url": "https://example.test/exported/10",
                "source_url": "https://example.test/exported/10",
                "created_at": "2026.05.18.",
                "collected_at": "2026-05-18T09:00:00+09:00",
                "source": "sample_archive_export",
                "title": "sample title",
                "posted_at": "2024.01.02.",
                "score": 0.91,
                "article_url": "https://cafe.naver.com/ArticleRead.nhn?clubid=1&articleid=10",
                "article_page_url": "/article?article_id=10",
            }
        ],
        "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        "estimated_cost": {"model": "gpt-4o-mini", "total_usd": 0.000003},
    }
    assert captured == {
        "query": "rate question",
        "top_k": 3,
        "model": "gpt-4o-mini",
        "embedding_model": "voyage-3-large",
        "qdrant_path": PROJECT_ROOT / "data" / "qdrant",
        "collection": "goodmorning_chunks",
        "project_root": PROJECT_ROOT,
    }


def test_success_response_preserves_source_metadata_without_archive_match(archive_db_path):
    record = {
        "answer": "answer",
        "sources": [
            {
                "chunk_id": "999:0",
                "article_id": 999,
                "url": "https://example.test/exported/999",
                "source_url": "https://example.test/exported/999",
                "created_at": "2026.05.18.",
                "collected_at": "2026-05-18T09:00:00+09:00",
                "posted_at": "2026.05.18.",
                "source": "sample_archive_export",
                "title": "exported title",
                "score": 0.7,
            }
        ],
        "usage": None,
        "estimated_cost": None,
    }

    payload = serve_rag_web.build_success_response(record, archive_db_path)

    assert payload["sources"][0] == {
        "chunk_id": "999:0",
        "article_id": 999,
        "url": "https://example.test/exported/999",
        "source_url": "https://example.test/exported/999",
        "created_at": "2026.05.18.",
        "collected_at": "2026-05-18T09:00:00+09:00",
        "posted_at": "2026.05.18.",
        "source": "sample_archive_export",
        "title": "exported title",
        "score": 0.7,
        "article_url": "https://example.test/exported/999",
        "article_page_url": "/article?article_id=999",
    }


@pytest.mark.parametrize("query", ["", "   "])
def test_post_answer_rejects_missing_query(monkeypatch, archive_db_path, query):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for invalid query")

    with RunningServer(monkeypatch, fake_run, archive_db_path) as server:
        status, _headers, body = server.request("POST", "/api/answer", {"query": query})

    payload = json.loads(body.decode("utf-8"))
    assert status == 400
    assert payload["ok"] is False
    assert "query" in payload["error"]


@pytest.mark.parametrize("top_k", [0, 21, "not-an-int"])
def test_post_answer_rejects_invalid_top_k(monkeypatch, archive_db_path, top_k):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for invalid top_k")

    with RunningServer(monkeypatch, fake_run, archive_db_path) as server:
        status, _headers, body = server.request("POST", "/api/answer", {"query": "question", "top_k": top_k})

    payload = json.loads(body.decode("utf-8"))
    assert status == 400
    assert payload["ok"] is False
    assert "top-k" in payload["error"]


def test_error_response_redacts_api_key_like_values(monkeypatch, archive_db_path):
    def fake_run(**kwargs):
        raise RuntimeError("provider failed for sk-test-secret OPENAI_API_KEY=abc123")

    with RunningServer(monkeypatch, fake_run, archive_db_path) as server:
        status, _headers, body = server.request("POST", "/api/answer", {"query": "question"})

    text = body.decode("utf-8")
    payload = json.loads(text)
    assert status == 500
    assert payload["ok"] is False
    assert "sk-test-secret" not in text
    assert "abc123" not in text
    assert "[redacted]" in payload["error"]


def test_article_page_renders_clean_text_and_escaped_fields(monkeypatch, tmp_path):
    db_path = create_archive_db(
        tmp_path / "archive.db",
        [
            sample_article(
                title="Title <script>alert(1)</script>",
                author="Author & Co",
                clean_text="clean <body> & text",
            )
        ],
    )

    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for article page")

    with RunningServer(monkeypatch, fake_run, db_path) as server:
        status, headers, body = server.request("GET", "/article?article_id=10")

    html = body.decode("utf-8")
    assert status == 200
    assert "text/html" in dict(headers)["Content-Type"]
    assert "Title &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "2024.01.02." in html
    assert "Author &amp; Co" in html
    assert "clean &lt;body&gt; &amp; text" in html
    assert "https://cafe.naver.com/ArticleRead.nhn?clubid=1&amp;articleid=10" in html
    assert "<script>alert(1)</script>" not in html


def test_article_page_rejects_non_numeric_article_id(monkeypatch, archive_db_path):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for article page")

    with RunningServer(monkeypatch, fake_run, archive_db_path) as server:
        status, _headers, body = server.request("GET", "/article?article_id=abc")

    assert status == 400
    assert "article_id must be a number" in body.decode("utf-8")


def test_article_page_returns_404_for_missing_article(monkeypatch, archive_db_path):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for article page")

    with RunningServer(monkeypatch, fake_run, archive_db_path) as server:
        status, _headers, body = server.request("GET", "/article?article_id=999999")

    assert status == 404
    assert "article not found" in body.decode("utf-8")


def test_article_page_escapes_raw_html_fallback(monkeypatch, tmp_path):
    db_path = create_archive_db(
        tmp_path / "archive.db",
        [
            sample_article(
                article_id=20,
                title="raw only",
                clean_text=None,
                raw_html="<script>alert('x')</script><p>raw</p>",
            )
        ],
    )

    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for article page")

    with RunningServer(monkeypatch, fake_run, db_path) as server:
        status, _headers, body = server.request("GET", "/article?article_id=20")

    html = body.decode("utf-8")
    assert status == 200
    assert "clean_text가 없어 raw_html을 escape 처리해 표시합니다." in html
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;&lt;p&gt;raw&lt;/p&gt;" in html
    assert "<script>alert('x')</script>" not in html


def test_server_uses_injected_archive_db_path(monkeypatch, tmp_path):
    db_path = create_archive_db(tmp_path / "archive.db", [sample_article()])

    def fake_run(**kwargs):
        return {
            "answer": "answer",
            "sources": [{"chunk_id": "10:0", "article_id": 10, "title": "sample title", "score": 0.9}],
            "usage": None,
            "estimated_cost": None,
        }

    with RunningServer(monkeypatch, fake_run, db_path) as server:
        assert server.server.archive_db_path == db_path
        assert server.server.archive_db_path != PROJECT_ROOT / "data" / "archive.db"
        status, _headers, body = server.request("POST", "/api/answer", {"query": "question"})

    payload = json.loads(body.decode("utf-8"))
    assert status == 200
    assert payload["sources"][0]["posted_at"] == "2024.01.02."
