import http.client
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import serve_rag_web


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class RunningServer:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, fake_run):
        monkeypatch.setattr(serve_rag_web, "run_rag_answer", fake_run)
        self.server = serve_rag_web.RagHTTPServer(
            ("127.0.0.1", 0),
            serve_rag_web.RagWebHandler,
            qdrant_path=serve_rag_web.DEFAULT_QDRANT_PATH,
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


def test_get_root_returns_html(monkeypatch):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for GET /")

    with RunningServer(monkeypatch, fake_run) as server:
        status, headers, body = server.request("GET", "/")

    html = body.decode("utf-8")
    assert status == 200
    assert "text/html" in dict(headers)["Content-Type"]
    assert "질문" in html
    assert "실행" in html
    assert "실행 시 Voyage/OpenAI API 호출 및 비용이 발생할 수 있음" in html


def test_post_answer_returns_mocked_result_and_expected_arguments(monkeypatch):
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
                    "title": "sample title",
                    "score": 0.91,
                }
            ],
            "model": kwargs["model"],
            "top_k": kwargs["top_k"],
            "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
            "estimated_cost": {"model": kwargs["model"], "total_usd": 0.000003},
        }

    with RunningServer(monkeypatch, fake_run) as server:
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
                "title": "sample title",
                "score": 0.91,
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


@pytest.mark.parametrize("query", ["", "   "])
def test_post_answer_rejects_missing_query(monkeypatch, query):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for invalid query")

    with RunningServer(monkeypatch, fake_run) as server:
        status, _headers, body = server.request("POST", "/api/answer", {"query": query})

    payload = json.loads(body.decode("utf-8"))
    assert status == 400
    assert payload["ok"] is False
    assert "query" in payload["error"]


@pytest.mark.parametrize("top_k", [0, 21, "not-an-int"])
def test_post_answer_rejects_invalid_top_k(monkeypatch, top_k):
    def fake_run(**kwargs):
        raise AssertionError("run_rag_answer should not be called for invalid top_k")

    with RunningServer(monkeypatch, fake_run) as server:
        status, _headers, body = server.request("POST", "/api/answer", {"query": "question", "top_k": top_k})

    payload = json.loads(body.decode("utf-8"))
    assert status == 400
    assert payload["ok"] is False
    assert "top-k" in payload["error"]


def test_error_response_redacts_api_key_like_values(monkeypatch):
    def fake_run(**kwargs):
        raise RuntimeError("provider failed for sk-test-secret OPENAI_API_KEY=abc123")

    with RunningServer(monkeypatch, fake_run) as server:
        status, _headers, body = server.request("POST", "/api/answer", {"query": "question"})

    text = body.decode("utf-8")
    payload = json.loads(text)
    assert status == 500
    assert payload["ok"] is False
    assert "sk-test-secret" not in text
    assert "abc123" not in text
    assert "[redacted]" in payload["error"]
