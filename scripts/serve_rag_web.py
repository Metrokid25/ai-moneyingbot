import argparse
import json
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_answering import DEFAULT_ANSWER_MODEL, run_rag_answer
from rag_retrieval import DEFAULT_COLLECTION, DEFAULT_MODEL, DEFAULT_TOP_K, validate_top_k


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]+"),
    re.compile(r"(OPENAI_API_KEY|VOYAGE_API_KEY)\s*=\s*[^,\s]+", re.IGNORECASE),
]


HTML_PAGE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ai-moneyingbot RAG</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, "Malgun Gothic", sans-serif;
      background: #f6f7f9;
      color: #20242a;
    }
    body {
      margin: 0;
    }
    main {
      max-width: 980px;
      margin: 0 auto;
      padding: 24px;
    }
    h1 {
      font-size: 24px;
      margin: 0 0 16px;
    }
    .notice {
      border-left: 4px solid #b45309;
      background: #fff7ed;
      padding: 12px 14px;
      margin-bottom: 18px;
    }
    .form-grid {
      display: grid;
      gap: 12px;
    }
    label {
      display: grid;
      gap: 6px;
      font-weight: 600;
    }
    textarea,
    input {
      box-sizing: border-box;
      width: 100%;
      border: 1px solid #c7ccd3;
      border-radius: 6px;
      padding: 10px;
      font: inherit;
      background: #ffffff;
    }
    textarea {
      min-height: 130px;
      resize: vertical;
    }
    .row {
      display: grid;
      grid-template-columns: 120px 1fr 1fr;
      gap: 12px;
    }
    button {
      width: fit-content;
      border: 0;
      border-radius: 6px;
      padding: 10px 16px;
      font: inherit;
      font-weight: 700;
      color: #ffffff;
      background: #2563eb;
      cursor: pointer;
    }
    button:disabled {
      background: #8da6dc;
      cursor: wait;
    }
    section {
      margin-top: 22px;
    }
    .panel {
      border: 1px solid #d7dce2;
      border-radius: 8px;
      background: #ffffff;
      padding: 14px;
      white-space: pre-wrap;
    }
    .error {
      color: #b91c1c;
      font-weight: 700;
    }
    .sources {
      display: grid;
      gap: 10px;
    }
    .source {
      border: 1px solid #d7dce2;
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
    }
    .source dl {
      display: grid;
      grid-template-columns: 110px 1fr;
      gap: 6px 10px;
      margin: 0;
    }
    .source dt {
      font-weight: 700;
      color: #3d4652;
    }
    .source dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    @media (max-width: 720px) {
      main {
        padding: 16px;
      }
      .row {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main>
    <h1>ai-moneyingbot 로컬 RAG UI</h1>
    <div class="notice">실행 시 Voyage/OpenAI API 호출 및 비용이 발생할 수 있음</div>
    <form id="rag-form" class="form-grid">
      <label>
        질문
        <textarea id="query" name="query" required></textarea>
      </label>
      <div class="row">
        <label>
          top-k
          <input id="top-k" name="top_k" type="number" min="1" max="20" value="5">
        </label>
        <label>
          model
          <input id="model" name="model" type="text" value="gpt-4o-mini">
        </label>
        <label>
          embedding_model
          <input id="embedding-model" name="embedding_model" type="text" value="voyage-3-large">
        </label>
      </div>
      <button id="run-button" type="submit">실행</button>
    </form>

    <section>
      <div id="status"></div>
      <div id="error" class="error"></div>
    </section>

    <section>
      <h2>답변</h2>
      <div id="answer" class="panel"></div>
    </section>

    <section>
      <h2>근거 chunks</h2>
      <div id="sources" class="sources"></div>
    </section>

    <section>
      <h2>사용량/예상 비용</h2>
      <div id="usage" class="panel"></div>
    </section>
  </main>
  <script>
    const form = document.getElementById("rag-form");
    const button = document.getElementById("run-button");
    const statusBox = document.getElementById("status");
    const errorBox = document.getElementById("error");
    const answerBox = document.getElementById("answer");
    const sourcesBox = document.getElementById("sources");
    const usageBox = document.getElementById("usage");

    function clearResults() {
      statusBox.textContent = "";
      errorBox.textContent = "";
      answerBox.textContent = "";
      usageBox.textContent = "";
      sourcesBox.replaceChildren();
    }

    function appendField(dl, name, value) {
      const dt = document.createElement("dt");
      dt.textContent = name;
      const dd = document.createElement("dd");
      dd.textContent = value == null ? "" : String(value);
      dl.append(dt, dd);
    }

    function renderSources(sources) {
      sourcesBox.replaceChildren();
      for (const source of sources || []) {
        const article = document.createElement("article");
        article.className = "source";
        const dl = document.createElement("dl");
        appendField(dl, "chunk_id", source.chunk_id);
        appendField(dl, "article_id", source.article_id);
        appendField(dl, "title", source.title);
        appendField(dl, "score", source.score);
        article.appendChild(dl);
        sourcesBox.appendChild(article);
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearResults();
      button.disabled = true;
      statusBox.textContent = "실행 중...";

      const payload = {
        query: document.getElementById("query").value,
        top_k: document.getElementById("top-k").value,
        model: document.getElementById("model").value,
        embedding_model: document.getElementById("embedding-model").value
      };

      try {
        const response = await fetch("/api/answer", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.ok) {
          errorBox.textContent = data.error || "요청 처리 중 오류가 발생했습니다.";
          return;
        }
        answerBox.textContent = data.answer || "";
        renderSources(data.sources);
        usageBox.textContent = JSON.stringify({
          usage: data.usage,
          estimated_cost: data.estimated_cost
        }, null, 2);
      } catch (error) {
        errorBox.textContent = "요청 처리 중 오류가 발생했습니다.";
      } finally {
        statusBox.textContent = "";
        button.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def parse_top_k(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_TOP_K
    try:
        top_k = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("--top-k must be an integer") from exc
    validate_top_k(top_k)
    return top_k


def sanitize_error(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    for pattern in SECRET_PATTERNS:
        message = pattern.sub("[redacted]", message)
    return message


def build_success_response(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "answer": record.get("answer", ""),
        "sources": record.get("sources", []),
        "usage": record.get("usage"),
        "estimated_cost": record.get("estimated_cost"),
    }


class RagWebHandler(BaseHTTPRequestHandler):
    server_version = "RagWeb/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        body = HTML_PAGE.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/answer":
            self.send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self.read_json_body()
            response = self.handle_answer(payload)
        except ValueError as exc:
            self.send_json({"ok": False, "error": sanitize_error(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self.send_json({"ok": False, "error": sanitize_error(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_json(response, HTTPStatus.OK)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") if raw else "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def handle_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        top_k = parse_top_k(payload.get("top_k"))
        model = str(payload.get("model") or DEFAULT_ANSWER_MODEL).strip() or DEFAULT_ANSWER_MODEL
        embedding_model = str(payload.get("embedding_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL

        record = run_rag_answer(
            query=query,
            top_k=top_k,
            model=model,
            embedding_model=embedding_model,
            qdrant_path=self.server.qdrant_path,
            collection=self.server.collection,
            project_root=self.server.project_root,
        )
        return build_success_response(record)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RagHTTPServer(HTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        qdrant_path: Path,
        collection: str,
        project_root: Path,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.qdrant_path = qdrant_path
        self.collection = collection
        self.project_root = project_root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ai-moneyingbot personal local web UI. This is not a public web server.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host for local use only. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port. Default: 8000")
    parser.add_argument("--qdrant-path", type=Path, default=DEFAULT_QDRANT_PATH)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    return parser.parse_args(argv)


def run_server(args: argparse.Namespace) -> None:
    server = RagHTTPServer(
        (args.host, args.port),
        RagWebHandler,
        qdrant_path=args.qdrant_path,
        collection=args.collection,
        project_root=PROJECT_ROOT,
    )
    host, port = server.server_address
    print(f"Serving ai-moneyingbot local UI at http://{host}:{port}/")
    print("This server is intended for personal localhost use only.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_server(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
