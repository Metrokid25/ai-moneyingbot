"""Read mentor articles from Archive DB and emit safe, paper-only watch signals."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SIGNAL_TYPES = {
    "ADD_WATCH", "REMOVE_WATCH", "DO_NOT_BUY", "EXIT_SIGNAL",
    "SECTOR_WATCH", "REVIEW_REQUIRED", "NO_SIGNAL",
}
_CODE_RE = re.compile(r"(?<![0-9A-Z])\d{4}[0-9A-Z]\d(?![0-9A-Z])")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+|[\r\n]+")
_POSITIVE_RE = re.compile(r"관심|주시|지켜|보겠|봅니다|봐야|매수\s*후보|좋아\s*보|좋습니다|픽")
_NEGATIVE_RE = re.compile(r"추격.{0,6}(?:금지|하지\s*마|말)|매수.{0,6}(?:금지|하지\s*마|말)|사지\s*마|접근.{0,4}금지")
_EXIT_RE = re.compile(r"정리|매도|익절|손절|비중\s*축소|관심.{0,4}(?:제외|삭제)")
_PAST_RE = re.compile(r"지난\s*(?:달|주|번)|예전에|말씀드렸|언급했|그때")
_NEWS_RE = re.compile(r"실적\s*발표|공시|뉴스|기사|보도")
_PREFERENCE_RE = re.compile(r"더\s*(?:좋아|낫|강해|유리)|선호")
_SECTORS = ("조선", "원전", "반도체", "바이오", "로봇", "방산", "자동차", "2차전지", "전력기기")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def normalize_text(value: str | None) -> str:
    value = html.unescape(_TAG_RE.sub(" ", value or ""))
    return _SPACE_RE.sub(" ", value).strip()


def revision_hash(body: str | None) -> str:
    return hashlib.sha256(normalize_text(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Stock:
    name: str
    code: str
    priority: int = 1


@dataclass
class Signal:
    schema_version: int
    article_id: str
    article_revision_hash: str
    author_id: str
    title: str
    source_url: str
    posted_at: str | None
    archived_at: str | None
    detected_at: str
    signal_type: str
    sector: str | None
    stocks: list[dict[str, Any]]
    confidence: float
    evidence: str
    parser_version: str
    mode: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StockMasterSnapshot:
    """Read-only stock-master snapshot (trading-bot cache v3 shape)."""

    def __init__(self, path: Path, aliases_path: Path | None = None) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        by_code = raw.get("by_code", raw)
        self.by_code = {str(c).upper(): str(n) for c, n in by_code.items() if c and n}
        self.by_name = {self.norm(n): c for c, n in self.by_code.items()}
        self.aliases: dict[str, str] = {}
        if aliases_path and aliases_path.exists():
            aliases = json.loads(aliases_path.read_text(encoding="utf-8"))
            for alias, target in aliases.items():
                code = str(target).upper()
                if code not in self.by_code:
                    code = self.by_name.get(self.norm(str(target)), "")
                if code:
                    self.aliases[self.norm(str(alias))] = code

    @staticmethod
    def norm(value: str) -> str:
        return re.sub(r"\s+", "", value).casefold()

    def candidates(self, text: str) -> list[Stock]:
        found: dict[str, Stock] = {}
        compact = self.norm(text)
        names = sorted(self.by_name, key=len, reverse=True)
        for normalized_name in names:
            # 1~2글자 상장명은 일반 문장 단어와 충돌하기 쉬우므로 자동 추출하지
            # 않는다. 명시 코드나 운영자 alias로만 허용하는 보수적 안전 기본값이다.
            if len(normalized_name) >= 3 and normalized_name in compact:
                code = self.by_name[normalized_name]
                found.setdefault(code, Stock(self.by_code[code], code))
        for alias, code in sorted(self.aliases.items(), key=lambda item: len(item[0]), reverse=True):
            if alias and alias in compact:
                found.setdefault(code, Stock(self.by_code[code], code))
        for code in _CODE_RE.findall(text.upper()):
            if code in self.by_code:
                found.setdefault(code, Stock(self.by_code[code], code))
        return list(found.values())

    def has_name_code_mismatch(self, text: str, stocks: list[Stock]) -> bool:
        for sentence in RuleParser._sentences(text):
            codes = [c for c in _CODE_RE.findall(sentence.upper()) if c in self.by_code]
            named = [
                s for s in stocks
                if self.norm(s.name) in self.norm(_CODE_RE.sub(" ", sentence.upper()))
            ]
            code_set = set(codes)
            named_set = {stock.code for stock in named}
            if code_set and named_set and code_set != named_set:
                return True
        return False


class RuleParser:
    def __init__(self, master: StockMasterSnapshot) -> None:
        self.master = master

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]

    def parse(self, *, article: sqlite3.Row, mode: str) -> Signal:
        title = normalize_text(article["title"])
        body = normalize_text(article["clean_text"] or article["raw_html"])
        combined = f"{title}. {body}".strip()
        stocks = self.master.candidates(combined)
        detected = now_iso()
        base = dict(
            schema_version=1,
            article_id=str(article["article_id"]),
            article_revision_hash=revision_hash(article["clean_text"] or article["raw_html"]),
            author_id=str(article["author"] or ""),
            title=title,
            source_url=str(article["url"] or ""),
            posted_at=article["posted_at"],
            archived_at=article["saved_at"],
            detected_at=detected,
            parser_version="mentor-signal-reader-v1",
            mode=mode,
        )

        if not body:
            return Signal(**base, signal_type="NO_SIGNAL", sector=None, stocks=[], confidence=1.0,
                          evidence="본문이 비어 있습니다")
        if self.master.has_name_code_mismatch(combined, stocks):
            return Signal(**base, signal_type="REVIEW_REQUIRED", sector=None,
                          stocks=[asdict(s) for s in stocks], confidence=0.0,
                          evidence="본문의 종목명과 6자리 종목코드가 일치하지 않습니다")

        sentences = self._sentences(combined)
        relevant: dict[str, list[str]] = {s.code: [] for s in stocks}
        for sentence in sentences:
            compact = self.master.norm(sentence)
            for stock in stocks:
                aliases = [n for n, c in self.master.aliases.items() if c == stock.code]
                if self.master.norm(stock.name) in compact or stock.code in sentence.upper() or any(a in compact for a in aliases):
                    relevant[stock.code].append(sentence)

        selected: list[Stock] = []
        negative: list[Stock] = []
        exits: list[Stock] = []
        for stock in stocks:
            context = " ".join(relevant[stock.code])
            if _EXIT_RE.search(context):
                exits.append(stock)
            elif _NEGATIVE_RE.search(context):
                negative.append(stock)
            elif _POSITIVE_RE.search(context) and not (_PAST_RE.search(context) or _NEWS_RE.search(context)):
                selected.append(stock)

        # "A보다 B가 더 좋다"에서는 선호 대상(B)만 남긴다.
        if _PREFERENCE_RE.search(combined) and "보다" in combined and len(stocks) >= 2:
            for sentence in sentences:
                if "보다" not in sentence or not _PREFERENCE_RE.search(sentence):
                    continue
                after = sentence.split("보다", 1)[1]
                preferred = [s for s in stocks if self.master.norm(s.name) in self.master.norm(after)]
                if len(preferred) == 1:
                    selected, negative, exits = preferred, [], []
                    break

        if selected and (negative or exits):
            return Signal(**base, signal_type="REVIEW_REQUIRED", sector=None,
                          stocks=[asdict(s) for s in stocks], confidence=0.4,
                          evidence="한 게시글에 신규 관심과 금지/정리 문맥이 함께 있습니다")
        if exits:
            return Signal(**base, signal_type="EXIT_SIGNAL", sector=None,
                          stocks=[asdict(s) for s in exits], confidence=0.99,
                          evidence=" ".join(relevant[exits[0].code])[:500])
        if negative:
            return Signal(**base, signal_type="DO_NOT_BUY", sector=None,
                          stocks=[asdict(s) for s in negative], confidence=0.99,
                          evidence=" ".join(relevant[negative[0].code])[:500])
        if selected:
            sector = next((s for s in _SECTORS if s in combined), None)
            return Signal(**base, signal_type="ADD_WATCH", sector=sector,
                          stocks=[asdict(s) for s in selected], confidence=0.97,
                          evidence=" ".join(relevant[selected[0].code])[:500])
        if not stocks:
            sector = next((s for s in _SECTORS if s in combined), None)
            if sector and _POSITIVE_RE.search(combined):
                return Signal(**base, signal_type="SECTOR_WATCH", sector=sector, stocks=[],
                              confidence=0.98, evidence=combined[:500])
        if _PAST_RE.search(combined) or _NEWS_RE.search(combined) or stocks:
            return Signal(**base, signal_type="NO_SIGNAL", sector=None, stocks=[],
                          confidence=0.95, evidence=combined[:500])
        return Signal(**base, signal_type="NO_SIGNAL", sector=None, stocks=[],
                      confidence=1.0, evidence="종목 또는 섹터 신호가 없습니다")


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS reader_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS mentor_signal_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id TEXT NOT NULL,
                article_revision_hash TEXT NOT NULL,
                stock_code TEXT NOT NULL DEFAULT '',
                signal_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence TEXT NOT NULL,
                posted_at TEXT,
                detected_at TEXT NOT NULL,
                processed_at TEXT,
                delivery_status TEXT NOT NULL,
                trading_response TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(article_id,article_revision_hash,stock_code,signal_type)
            );
        """)

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM reader_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO reader_meta VALUES (?,?)", (key, value))
        self.conn.commit()

    def insert_event(self, payload: dict[str, Any], stock: dict[str, Any] | None) -> tuple[int, bool]:
        now = now_iso()
        code = stock["code"] if stock else ""
        event_payload = {**payload, "stock_name": stock["name"] if stock else "",
                         "stock_code": code}
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO mentor_signal_events "
            "(article_id,article_revision_hash,stock_code,signal_type,confidence,evidence,"
            "posted_at,detected_at,delivery_status,payload_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (payload["article_id"], payload["article_revision_hash"], code,
             payload["signal_type"], payload["confidence"], payload["evidence"],
             payload.get("posted_at"), payload["detected_at"], "pending",
             json.dumps(event_payload, ensure_ascii=False), now, now),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM mentor_signal_events WHERE article_id=? AND article_revision_hash=? "
            "AND stock_code=? AND signal_type=?",
            (payload["article_id"], payload["article_revision_hash"], code, payload["signal_type"]),
        ).fetchone()
        return int(row[0]), cur.rowcount == 1

    def mark(self, event_id: int, status: str, response: str = "") -> None:
        now = now_iso()
        self.conn.execute(
            "UPDATE mentor_signal_events SET delivery_status=?,trading_response=?,"
            "processed_at=?,updated_at=? WHERE id=?", (status, response, now, now, event_id)
        )
        self.conn.commit()

    def pending(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id,payload_json FROM mentor_signal_events "
            "WHERE delivery_status IN ('pending','delivery_failed') AND stock_code!='' ORDER BY id"
        ).fetchall()


class ArchiveSource:
    REQUIRED = {"article_id", "title", "url", "author", "posted_at", "raw_html",
                "clean_text", "status", "saved_at", "updated_at"}

    def __init__(self, path: Path) -> None:
        uri = path.resolve().as_uri() + "?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True, timeout=15)
        self.conn.row_factory = sqlite3.Row
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(articles)")}
        missing = self.REQUIRED - cols
        if missing:
            raise RuntimeError(f"Archive DB schema missing columns: {sorted(missing)}")

    def max_article_id(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(article_id),0) FROM articles").fetchone()
        return int(row[0])

    def fetch(self, author: str, after_id: int, updated_since: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT article_id,title,url,author,posted_at,raw_html,clean_text,status,saved_at,updated_at "
            "FROM articles WHERE author=? AND status IN ('BODY_COLLECTED','OK') "
            "AND COALESCE(clean_text,raw_html,'')!='' "
            "AND (article_id>? OR julianday(COALESCE(updated_at,saved_at))>=julianday(?)) "
            "ORDER BY article_id", (author, after_id, updated_since)
        ).fetchall()


def deliver(payload: dict[str, Any], base_url: str, web_key: str, timeout: float = 15.0) -> tuple[bool, str]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/signals/mentor",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Web-Key": web_key}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        return 200 <= response.status < 300, body
    except urllib.error.HTTPError as exc:
        return False, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # network failures are retried on the next cycle
        return False, f"{type(exc).__name__}: {exc}"


class MentorSignalReader:
    def __init__(self, *, archive: ArchiveSource, state: StateStore, parser: RuleParser,
                 author_id: str, mode: str, confidence_threshold: float,
                 trading_base_url: str = "", web_key: str = "",
                 notifier: Callable[[str], bool] | None = None) -> None:
        if mode == "live":
            raise ValueError("Live mentor signal trading is disabled by policy.")
        if mode not in {"shadow", "paper"}:
            raise ValueError("mode must be shadow or paper")
        if not author_id:
            raise ValueError("MENTOR_AUTHOR_ID is required")
        self.archive, self.state, self.parser = archive, state, parser
        self.author_id, self.mode = author_id, mode
        self.threshold = confidence_threshold
        self.trading_base_url, self.web_key = trading_base_url, web_key
        self.notifier = notifier

    def _notify(self, signal: dict[str, Any], status: str) -> None:
        if not self.notifier:
            return
        names = ", ".join(f"{s['name']}({s['code']})" for s in signal["stocks"]) or "없음"
        heading = "[멘토 픽 자동등록 · PAPER]" if self.mode == "paper" else "[멘토 글 판독 · SHADOW]"
        self.notifier(
            f"{heading}\n\n글: {signal['title']}\n판독: {signal['signal_type']}\n"
            f"종목: {names}\n신뢰도: {signal['confidence']:.0%}\n근거: {signal['evidence']}\n처리: {status}"
        )

    def _send_event(self, event_id: int, payload: dict[str, Any]) -> None:
        if self.mode == "shadow":
            self.state.mark(event_id, "shadow")
            return
        if payload["signal_type"] != "ADD_WATCH" or payload["confidence"] < self.threshold:
            self.state.mark(event_id, "not_eligible")
            return
        if not self.trading_base_url or not self.web_key:
            self.state.mark(event_id, "delivery_failed", "Trading API configuration missing")
            return
        outbound = {
            key: payload.get(key) for key in (
                "article_id", "article_revision_hash", "author_id", "posted_at", "detected_at",
                "stock_name", "stock_code", "sector", "signal_type", "confidence", "evidence",
                "source_url", "mode",
            )
        }
        ok, response = deliver(outbound, self.trading_base_url, self.web_key)
        self.state.mark(event_id, "delivered" if ok else "delivery_failed", response)

    def run_once(self, *, bootstrap_existing: bool = False) -> dict[str, int]:
        if self.state.get_meta("initialized") is None:
            baseline = 0 if bootstrap_existing else self.archive.max_article_id()
            watermark = "1970-01-01T00:00:00+00:00" if bootstrap_existing else now_iso()
            self.state.set_meta("last_article_id", str(baseline))
            self.state.set_meta("last_scan_at", watermark)
            self.state.set_meta("initialized", "1")
            if not bootstrap_existing:
                return {"articles": 0, "events": 0, "delivered": 0, "duplicates": 0}

        # Retry delivery failures without rereading or modifying Archive DB.
        for row in self.state.pending():
            self._send_event(row["id"], json.loads(row["payload_json"]))

        after_id = int(self.state.get_meta("last_article_id") or 0)
        updated_since = self.state.get_meta("last_scan_at") or "1970-01-01T00:00:00+00:00"
        scan_started = now_iso()
        articles = self.archive.fetch(self.author_id, after_id, updated_since)
        counts = {"articles": len(articles), "events": 0, "delivered": 0, "duplicates": 0}
        max_id = after_id
        for article in articles:
            max_id = max(max_id, int(article["article_id"]))
            signal = self.parser.parse(article=article, mode=self.mode).as_dict()
            stocks = signal["stocks"] or [None]
            article_statuses: list[str] = []
            for stock in stocks:
                event_id, inserted = self.state.insert_event(signal, stock)
                if not inserted:
                    counts["duplicates"] += 1
                    existing_status = self.state.conn.execute(
                        "SELECT delivery_status FROM mentor_signal_events WHERE id=?", (event_id,)
                    ).fetchone()
                    article_statuses.append(existing_status[0])
                    continue
                counts["events"] += 1
                payload = {**signal, "stock_name": stock["name"] if stock else "",
                           "stock_code": stock["code"] if stock else ""}
                self._send_event(event_id, payload)
                row = self.state.conn.execute(
                    "SELECT delivery_status FROM mentor_signal_events WHERE id=?", (event_id,)
                ).fetchone()
                article_statuses.append(row[0])
                if row[0] == "delivered":
                    counts["delivered"] += 1
            if self.mode == "shadow":
                notify_status = "관심종목 미등록"
            elif "delivered" in article_statuses:
                notify_status = "관심종목 등록 성공 · Paper Runner 감시 대기 · 실전 주문 비활성"
            elif "delivery_failed" in article_statuses:
                notify_status = "관심종목 등록 실패 · 다음 주기 재시도 · 실전 주문 비활성"
            else:
                notify_status = "자동등록 대상 아님 · 실전 주문 비활성"
            self._notify(signal, notify_status)
        self.state.set_meta("last_article_id", str(max_id))
        self.state.set_meta("last_scan_at", scan_started)
        return counts

    def run_loop(self, poll_seconds: int) -> None:
        while True:
            try:
                print(json.dumps(self.run_once(), ensure_ascii=False))
            except (OSError, RuntimeError, sqlite3.Error) as exc:
                # 일시 DB 잠금/읽기 실패로 상주 프로세스가 죽지 않는다. 체크포인트는
                # 성공한 run_once 끝에서만 이동하므로 다음 주기에 그대로 재시도한다.
                print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
            time.sleep(max(1, poll_seconds))
