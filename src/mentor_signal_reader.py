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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


SIGNAL_TYPES = {
    "ADD_WATCH", "REMOVE_WATCH", "DO_NOT_BUY", "EXIT_SIGNAL",
    "SECTOR_WATCH", "REVIEW_REQUIRED", "NO_SIGNAL",
}
_CODE_RE = re.compile(r"(?<![0-9A-Z])\d{4}[0-9A-Z]\d(?![0-9A-Z])")
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAG_RE = re.compile(r"</?(?:p|div|br|li|tr|h[1-6])\b[^>]*>", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+|[\r\n]+")
_CLAUSE_RE = re.compile(
    r"[,，;；]|\s+(?:그리고|반면)\s+|(?<=말고)\s+|(?<=대신)\s+|(?<=대신에)\s+"
)
_POSITIVE_RE = re.compile(
    r"관심|주시|지켜|보겠|봅니다|봐야|살펴|체크|공략|담아|편입|홀딩|"
    r"갈아\s*타|재진입|다시\s*(?:담|편입|매수)|분할\s*매수|"
    r"매수\s*(?:후보|가능|대응|사인)|좋아\s*보|좋습니다|픽"
)
_NEGATIVE_RE = re.compile(r"추격.{0,6}(?:금지|하지\s*마|말)|매수.{0,6}(?:금지|하지\s*마|말)|사지\s*마|접근.{0,4}금지")
_EXCLUSION_RE = re.compile(r"(?:말고|대신(?:에)?)(?:\s|$)")
_EXIT_ACTION_RE = re.compile(
    r"수익\s*실현(?:\s*(?:하고|후|합니다|하겠|해야|하세요|사인|에\s*나서|으로\s*대응))|"
    r"비중\s*축소|관심.{0,4}(?:제외|삭제)|"
    r"(?:익절|손절)(?:\s*(?:합니다|하겠|해야|하세요|사인|로\s*대응))|"
    r"(?:전량|일부)\s*(?:정리|매도)|"
    r"(?:정리|매도)(?:\s*(?:합니다|하겠|해야|하세요|합시다|사인|로\s*대응))"
)
_EXIT_MENTION_RE = re.compile(r"(?<!공)매도|정리|익절|손절|수익\s*실현|비중\s*축소")
_ACTION_NEGATION_RE = re.compile(
    r"(?:매도|정리|익절|손절|수익\s*실현|비중\s*축소).{0,12}"
    r"(?:아니|않|해당\s*되지|할\s*필요\s*없)"
)
_CONDITIONAL_EXIT_RE = re.compile(
    r"(?:매도|정리|익절|손절|수익\s*실현|비중\s*축소)(?:이|가)?\s*(?:나온다면|나오면|경우)"
)
_STRONG_POSITIVE_RE = re.compile(
    r"관심|주시|공략|담아|편입|홀딩|갈아\s*타|재진입|분할\s*매수|매수\s*(?:후보|가능|대응|사인)"
)
_POSITIVE_NEGATION_RE = re.compile(
    r"(?:관심|주시|지켜|살펴|체크|공략|편입|홀딩|매수\s*사인|좋아\s*보).{0,12}"
    r"(?:아니|아닙|아님|없|않|하지\s*마|말)"
)
_NEGATION_SUFFIX_RE = re.compile(
    r"^(?:.{0,12})(?:아니|아닙|아님|없|않|안(?:\s|$)|어렵|하지\s*마|지\s*마|말)"
)
_THIRD_PARTY_EXIT_RE = re.compile(
    r"(?:외인|외국인|기관|개인|세력).{0,30}(?:일부\s*|전량\s*)?(?<!공)매도"
)
_MARKET_METRIC_RE = re.compile(r"공매도|외인|외국인|기관|개인|수급")
_PAST_RE = re.compile(r"지난\s*(?:달|주|번)|예전에|말씀드렸|언급했|그때")
_NEWS_RE = re.compile(r"실적\s*발표|공시|뉴스|기사|보도")
_PREFERENCE_RE = re.compile(r"더\s*(?:좋아|낫|강해|유리)|선호")
_FEATURE_TITLE_RE = re.compile(r"특징\s*주")
_MACRO_TITLE_RE = re.compile(r"^\s*(?:오늘\s*은|이번\s*주\s*는|다음\s*주\s*는)")
_BULLET_RE = re.compile(r"^\s*[-–—•·*▶▷◆◇■□▪◦]+\s*")
_SECTORS = ("조선", "원전", "반도체", "바이오", "로봇", "방산", "자동차", "2차전지", "전력기기")
_KST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def normalize_text(value: str | None) -> str:
    value = html.unescape(_TAG_RE.sub(" ", value or ""))
    return _SPACE_RE.sub(" ", value).strip()


def text_lines(value: str | None) -> list[str]:
    """Preserve semantic line/list boundaries while removing HTML noise."""
    value = _BLOCK_TAG_RE.sub("\n", value or "")
    value = html.unescape(_TAG_RE.sub(" ", value))
    return [normalize_text(line) for line in value.splitlines() if normalize_text(line)]


def normalize_timestamp(value: str | None) -> str | None:
    """Convert Archive's legacy KST strings to timezone-aware ISO-8601."""
    raw = normalize_text(value)
    if not raw:
        return None
    cleaned = re.sub(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})\.?(?=\s|$)", r"\1-\2-\3", raw)
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_KST)
    return parsed.isoformat()


def revision_hash(title: str | None, body: str | None = None) -> str:
    # 제목 자체가 픽인 글이 많으므로 제목 수정도 새 revision이어야 한다.
    # 줄 경계도 특징주/시황 하단 종목블록 판독 의미의 일부다.
    canonical_body = "\n".join(text_lines(body))
    canonical = f"{normalize_text(title)}\n{canonical_body}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        self.tokens_by_code: dict[str, set[str]] = {
            code: {self.norm(name)} for code, name in self.by_code.items()
        }
        for alias, code in self.aliases.items():
            self.tokens_by_code.setdefault(code, set()).add(alias)
        # 표준 re alternation은 겹치는 한글 종목명 수천 개에서 역추적 비용이 커진다.
        # 작은 trie를 한 번 만들고 본문을 선형 스캔한다.
        self._trie: list[dict[str, int]] = [{}]
        self._trie_outputs: list[list[str]] = [[]]
        for token, code in {
            **{token: code for token, code in self.by_name.items() if len(token) >= 3},
            **{token: code for token, code in self.aliases.items() if token},
        }.items():
            node = 0
            for char in token:
                next_node = self._trie[node].get(char)
                if next_node is None:
                    next_node = len(self._trie)
                    self._trie[node][char] = next_node
                    self._trie.append({})
                    self._trie_outputs.append([])
                node = next_node
            if code not in self._trie_outputs[node]:
                self._trie_outputs[node].append(code)

    @staticmethod
    def norm(value: str) -> str:
        return re.sub(r"\s+", "", value).casefold()

    def candidates(self, text: str) -> list[Stock]:
        found: dict[str, Stock] = {}
        compact = self.norm(text)
        start = 0
        while start < len(compact):
            node = 0
            longest_codes: list[str] = []
            longest_end = start
            for position in range(start, len(compact)):
                char = compact[position]
                next_node = self._trie[node].get(char)
                if next_node is None:
                    break
                node = next_node
                if self._trie_outputs[node]:
                    longest_codes = self._trie_outputs[node]
                    longest_end = position + 1
            if longest_codes:
                for code in longest_codes:
                    found.setdefault(code, Stock(self.by_code[code], code))
                start = longest_end
            else:
                start += 1
        for code in _CODE_RE.findall(text.upper()):
            if code in self.by_code:
                found.setdefault(code, Stock(self.by_code[code], code))
        return list(found.values())

    def exact_stock(self, value: str) -> Stock | None:
        token = _BULLET_RE.sub("", normalize_text(value))
        token = token.strip(" -–—•·*▶▷◆◇■□▪◦.,:;()[]{}<>")
        normalized = self.norm(token)
        code = self.by_name.get(normalized) or self.aliases.get(normalized)
        if code:
            return Stock(self.by_code[code], code)
        if normalized.upper() in self.by_code:
            code = normalized.upper()
            return Stock(self.by_code[code], code)
        codes = [code for code in _CODE_RE.findall(token.upper()) if code in self.by_code]
        if len(codes) == 1:
            code = codes[0]
            name_part = _CODE_RE.sub("", token.upper()).strip(" -–—•·*.,:;()[]{}<>")
            resolved = self.by_name.get(self.norm(name_part)) or self.aliases.get(self.norm(name_part))
            if not name_part or resolved == code:
                return Stock(self.by_code[code], code)
        return None

    def mentions(self, stock: Stock, text: str) -> bool:
        compact = self.norm(text)
        return (stock.code in text.upper()
                or any(token in compact for token in self.tokens_by_code.get(stock.code, ())))

    def has_name_code_mismatch(self, text: str, stocks: list[Stock]) -> bool:
        for sentence in RuleParser._sentences(text):
            codes = [c for c in _CODE_RE.findall(sentence.upper()) if c in self.by_code]
            named = self.candidates(_CODE_RE.sub(" ", sentence.upper()))
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

    @staticmethod
    def _line_action(line: str) -> str | None:
        positive_matches = list(_POSITIVE_RE.finditer(line))
        negated_positive_starts = {
            match.start() for match in positive_matches
            if _NEGATION_SUFFIX_RE.search(line[match.end():match.end() + 20])
        }
        actions: list[tuple[int, str]] = [
            (start, "NO_SIGNAL") for start in negated_positive_starts
        ]
        actions.extend((match.start(), "DO_NOT_BUY") for match in _EXCLUSION_RE.finditer(line))
        if not _ACTION_NEGATION_RE.search(line):
            third_party_spans = [match.span() for match in _THIRD_PARTY_EXIT_RE.finditer(line)]
            actions.extend(
                (match.start(), "EXIT_SIGNAL") for match in _EXIT_ACTION_RE.finditer(line)
                if not any(start <= match.start() < end for start, end in third_party_spans)
            )
        actions.extend((match.start(), "DO_NOT_BUY") for match in _NEGATIVE_RE.finditer(line))
        weak_market_check = _MARKET_METRIC_RE.search(line) and not _STRONG_POSITIVE_RE.search(line)
        if not weak_market_check and not (
            _CONDITIONAL_EXIT_RE.search(line) and not _STRONG_POSITIVE_RE.search(line)
        ):
            actions.extend(
                (match.start(), "ADD_WATCH") for match in positive_matches
                if match.start() not in negated_positive_starts
            )
        # 한 문장에 이전 비중축소와 현재 재매수가 함께 있으면 뒤쪽 행동을 현재
        # 결론으로 본다. 아카이브의 실제 문장 순서와 일치한다.
        if actions:
            return max(actions, key=lambda item: item[0])[1]
        # 단순 외인/기관 매도, 공매도 설명은 EXIT가 아니지만 특징주 기본
        # ADD로 되살려서도 안 되므로 명시적인 중립 차단값을 반환한다.
        if _PAST_RE.search(line) or _NEWS_RE.search(line) or _EXIT_MENTION_RE.search(line):
            return "NO_SIGNAL"
        return None

    def parse_all(self, *, article: sqlite3.Row, mode: str) -> list[Signal]:
        title = normalize_text(article["title"])
        raw_body = article["clean_text"] or article["raw_html"] or ""
        lines = text_lines(raw_body)
        # Archive clean_text의 첫 줄에는 제목이 중복되는 경우가 대부분이다.
        if lines and self.master.norm(lines[0].strip(" .,:;")) == self.master.norm(title.strip(" .,:;")):
            lines = lines[1:]
        body = " ".join(lines)
        combined = f"{title}. {body}".strip()
        stocks = self.master.candidates(combined)
        detected = now_iso()
        base = dict(
            schema_version=1,
            article_id=str(article["article_id"]),
            article_revision_hash=revision_hash(title, raw_body),
            author_id=str(article["author"] or ""),
            title=title,
            source_url=str(article["url"] or ""),
            posted_at=normalize_timestamp(article["posted_at"]),
            archived_at=normalize_timestamp(article["saved_at"]),
            detected_at=detected,
            parser_version="mentor-signal-reader-v1",
            mode=mode,
        )

        if self.master.has_name_code_mismatch(combined, stocks):
            return [Signal(**base, signal_type="REVIEW_REQUIRED", sector=None,
                           stocks=[asdict(s) for s in stocks], confidence=0.0,
                           evidence="본문의 종목명과 6자리 종목코드가 일치하지 않습니다")]

        exact_title = self.master.exact_stock(title)
        feature_title = bool(_FEATURE_TITLE_RE.search(title))
        macro_title = bool(_MACRO_TITLE_RE.search(title))
        origin: dict[str, set[str]] = {s.code: set() for s in stocks}
        if exact_title:
            origin.setdefault(exact_title.code, set()).add("exact_title")
            if all(s.code != exact_title.code for s in stocks):
                stocks.insert(0, exact_title)

        tail_start = int(len(lines) * 0.75)
        line_candidates: list[list[Stock]] = []
        for index, line in enumerate(lines):
            line_stocks = self.master.candidates(line)
            line_candidates.append(line_stocks)
            exact_line = self.master.exact_stock(line)
            structured = bool(exact_line or _BULLET_RE.match(line))
            for stock in line_stocks:
                origin.setdefault(stock.code, set())
                if feature_title and structured:
                    origin[stock.code].add("feature_list")
                if macro_title and index >= tail_start and structured:
                    origin[stock.code].add("macro_tail")

        contexts: dict[str, list[str]] = {s.code: [] for s in stocks}
        all_context_lines = [title, *lines]
        all_context_candidates = [self.master.candidates(title), *line_candidates]
        for index, (line, mentioned_stocks) in enumerate(zip(all_context_lines, all_context_candidates)):
            for stock in mentioned_stocks:
                if stock.code not in contexts:
                    continue
                sentence_contexts = []
                for sentence in self._sentences(line):
                    clauses = [part.strip() for part in _CLAUSE_RE.split(sentence) if part.strip()]
                    sentence_contexts.extend(
                        clause for clause in clauses if self.master.mentions(stock, clause)
                    )
                sentence_contexts = sentence_contexts or [line]
                # 종목 단독 행은 바로 다음 설명문까지 같은 블록으로 본다. 다만 다음
                # 행이 다른 종목을 명시하면 그 종목의 행동을 섞지 않는다.
                exact = self.master.exact_stock(line)
                if exact and exact.code == stock.code and index + 1 < len(all_context_lines):
                    following = all_context_lines[index + 1]
                    following_stocks = all_context_candidates[index + 1]
                    if not following_stocks or all(s.code == stock.code for s in following_stocks):
                        sentence_contexts = [f"{line} {following}"]
                contexts[stock.code].extend(sentence_contexts)

        decisions: dict[str, str] = {}
        evidence_by_code: dict[str, str] = {}
        confidence_by_code: dict[str, float] = {}
        for stock in stocks:
            relevant = contexts.get(stock.code, [])
            decision = None
            evidence = relevant[-1] if relevant else title
            # 가장 뒤의 명시적 대응 문장이 현재 의견으로 우선한다.
            for context in reversed(relevant):
                action = self._line_action(context)
                if action is not None:
                    decision, evidence = action, context
                    break
            if decision is None or (
                decision == "NO_SIGNAL" and not body
                and "exact_title" in origin.get(stock.code, set())
            ):
                stock_origin = origin.get(stock.code, set())
                if "exact_title" in stock_origin:
                    decision, evidence = "ADD_WATCH", title
                    confidence_by_code[stock.code] = 0.995
                elif "feature_list" in stock_origin:
                    decision = "ADD_WATCH"
                    confidence_by_code[stock.code] = 0.98
                elif "macro_tail" in stock_origin:
                    decision = "ADD_WATCH"
                    confidence_by_code[stock.code] = 0.96
            if decision and decision != "NO_SIGNAL":
                decisions[stock.code] = decision
                evidence_by_code[stock.code] = evidence[:500]
                confidence_by_code.setdefault(stock.code, 0.99 if decision != "ADD_WATCH" else 0.97)

        # "A보다 B가 더 좋다"는 비교 대상 A를 픽에서 제외하고 B만 남긴다.
        for sentence in self._sentences(combined):
            if "보다" not in sentence or not _PREFERENCE_RE.search(sentence):
                continue
            before, after = sentence.split("보다", 1)
            preferred_codes = {s.code for s in self.master.candidates(after)}
            compared_codes = {s.code for s in self.master.candidates(before)}
            preferred = [s for s in stocks if s.code in preferred_codes]
            compared = [s for s in stocks if s.code in compared_codes]
            if len(preferred) == 1:
                decisions[preferred[0].code] = "ADD_WATCH"
                confidence_by_code[preferred[0].code] = 0.98
                evidence_by_code[preferred[0].code] = sentence[:500]
                for stock in compared:
                    if decisions.get(stock.code) == "ADD_WATCH":
                        decisions.pop(stock.code, None)

        sector = next((s for s in _SECTORS if s in combined), None)
        signals: list[Signal] = []
        for signal_type in ("EXIT_SIGNAL", "DO_NOT_BUY", "ADD_WATCH"):
            grouped = [s for s in stocks if decisions.get(s.code) == signal_type]
            if not grouped:
                continue
            confidence = min(confidence_by_code[s.code] for s in grouped)
            evidence = " | ".join(dict.fromkeys(evidence_by_code[s.code] for s in grouped))[:500]
            signals.append(Signal(
                **base, signal_type=signal_type, sector=sector if signal_type == "ADD_WATCH" else None,
                stocks=[asdict(s) for s in grouped], confidence=confidence, evidence=evidence,
            ))
        if signals:
            return signals
        if sector and _POSITIVE_RE.search(combined) and not stocks:
            return [Signal(**base, signal_type="SECTOR_WATCH", sector=sector, stocks=[],
                           confidence=0.98, evidence=combined[:500])]
        evidence = "본문이 비어 있습니다" if not body else (combined[:500] or "종목 또는 섹터 신호가 없습니다")
        return [Signal(**base, signal_type="NO_SIGNAL", sector=None, stocks=[],
                       confidence=1.0 if not stocks else 0.95, evidence=evidence)]

    def parse(self, *, article: sqlite3.Row, mode: str) -> Signal:
        signals = self.parse_all(article=article, mode=mode)
        if len(signals) == 1:
            return signals[0]
        # 단일 결과 API를 사용하는 호출자는 혼합 행동을 자동 실행하지 못하게 한다.
        first = signals[0]
        stocks = [stock for signal in signals for stock in signal.stocks]
        return Signal(
            schema_version=first.schema_version, article_id=first.article_id,
            article_revision_hash=first.article_revision_hash, author_id=first.author_id,
            title=first.title, source_url=first.source_url, posted_at=first.posted_at,
            archived_at=first.archived_at, detected_at=first.detected_at,
            signal_type="REVIEW_REQUIRED", sector=None, stocks=stocks, confidence=0.4,
            evidence="한 게시글에 서로 다른 종목 행동이 함께 있습니다",
            parser_version=first.parser_version, mode=first.mode,
        )


class StateStore:
    def __init__(self, path: Path, forbidden_path: Path | None = None) -> None:
        self.path = path.resolve()
        if forbidden_path is not None and self.path == forbidden_path.resolve():
            raise ValueError("MENTOR_SIGNAL_STATE_DB must not be the Archive DB")
        if self.path.exists():
            probe = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
            try:
                archive_table = probe.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='articles'"
                ).fetchone()
            finally:
                probe.close()
            if archive_table:
                raise ValueError("MENTOR_SIGNAL_STATE_DB must not be an Archive DB")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=15000")
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
                delivery_attempts INTEGER NOT NULL DEFAULT 0,
                next_retry_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(article_id,article_revision_hash,stock_code,signal_type)
            );
        """)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(mentor_signal_events)")}
        if "delivery_attempts" not in columns:
            self.conn.execute(
                "ALTER TABLE mentor_signal_events ADD COLUMN delivery_attempts INTEGER NOT NULL DEFAULT 0"
            )
        if "next_retry_at" not in columns:
            self.conn.execute("ALTER TABLE mentor_signal_events ADD COLUMN next_retry_at TEXT")
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM reader_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO reader_meta VALUES (?,?)", (key, value))
        self.conn.commit()

    def initialize(self, *, last_article_id: int, last_scan_at: str) -> None:
        """Create the first checkpoint atomically so a crash cannot half-initialize it."""
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO reader_meta(key,value) VALUES (?,?)",
                (("last_article_id", str(last_article_id)),
                 ("last_scan_at", last_scan_at), ("initialized", "1")),
            )

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
        response = response[:10000]
        self.conn.execute(
            "UPDATE mentor_signal_events SET delivery_status=?,trading_response=?,"
            "processed_at=?,next_retry_at=NULL,updated_at=? WHERE id=?",
            (status, response, now, now, event_id)
        )
        self.conn.commit()

    def mark_failure(self, event_id: int, response: str) -> None:
        row = self.conn.execute(
            "SELECT delivery_attempts FROM mentor_signal_events WHERE id=?", (event_id,)
        ).fetchone()
        attempts = int(row[0] if row else 0) + 1
        delay_seconds = min(3600, 30 * (2 ** min(attempts - 1, 7)))
        retry_at = (datetime.now(timezone.utc).astimezone() + timedelta(seconds=delay_seconds)).isoformat()
        now = now_iso()
        self.conn.execute(
            "UPDATE mentor_signal_events SET delivery_status='delivery_failed',"
            "trading_response=?,delivery_attempts=?,next_retry_at=?,updated_at=? WHERE id=?",
            (response[:10000], attempts, retry_at, now, event_id),
        )
        self.conn.commit()

    def pending(self, limit: int = 10) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id,payload_json FROM mentor_signal_events "
            "WHERE delivery_status IN ('pending','delivery_failed') AND stock_code!='' "
            "AND (next_retry_at IS NULL OR julianday(next_retry_at)<=julianday(?)) "
            "ORDER BY id LIMIT ?", (now_iso(), max(1, limit))
        ).fetchall()


class ArchiveSource:
    REQUIRED = {"article_id", "title", "url", "author", "posted_at", "raw_html",
                "clean_text", "status", "saved_at", "updated_at"}

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        uri = self.path.as_uri() + "?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA query_only=ON")
        if self.conn.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise RuntimeError("Archive DB query_only guard could not be enabled")
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(articles)")}
        missing = self.REQUIRED - cols
        if missing:
            raise RuntimeError(f"Archive DB schema missing columns: {sorted(missing)}")

    def max_article_id(self, author: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(article_id),0) FROM articles WHERE author=?", (author,)
        ).fetchone()
        return int(row[0])

    def fetch(self, author: str, after_id: int, updated_since: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT article_id,title,url,author,posted_at,raw_html,clean_text,status,saved_at,updated_at "
            "FROM articles WHERE author=? AND status IN ('BODY_COLLECTED','OK') "
            "AND (article_id>? OR julianday(COALESCE(updated_at,saved_at))>julianday(?)) "
            "ORDER BY article_id", (author, after_id, updated_since)
        ).fetchall()


def deliver(
    payload: dict[str, Any], base_url: str, web_key: str, timeout: float = 15.0
) -> tuple[bool, str, bool]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/signals/mentor",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Web-Key": web_key}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        return 200 <= response.status < 300, body, False
    except urllib.error.HTTPError as exc:
        retryable = exc.code in {408, 409, 425, 429} or exc.code >= 500
        return False, exc.read().decode("utf-8", errors="replace"), retryable
    except Exception as exc:  # network failures are retried on the next cycle
        return False, f"{type(exc).__name__}: {exc}", True


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
        if archive.path == state.path:
            raise ValueError("MENTOR_SIGNAL_STATE_DB must not be the Archive DB")
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence threshold must be between 0 and 1")
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
        try:
            self.notifier(
                f"{heading}\n\n글: {signal['title']}\n판독: {signal['signal_type']}\n"
                f"종목: {names}\n신뢰도: {signal['confidence']:.0%}\n근거: {signal['evidence']}\n처리: {status}"
            )
        except Exception as exc:
            # Telegram 장애가 체크포인트/Trading 전달을 되돌려서는 안 된다.
            print(json.dumps({"notification_error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))

    def _send_event(self, event_id: int, payload: dict[str, Any]) -> str:
        if self.mode == "shadow":
            self.state.mark(event_id, "shadow")
            return "shadow"
        if payload["signal_type"] != "ADD_WATCH" or payload["confidence"] < self.threshold:
            self.state.mark(event_id, "not_eligible")
            return "not_eligible"
        if not self.trading_base_url or not self.web_key:
            self.state.mark(event_id, "delivery_rejected", "Trading API configuration missing")
            return "delivery_rejected"
        outbound = {
            key: payload.get(key) for key in (
                "article_id", "article_revision_hash", "author_id", "posted_at", "detected_at",
                "stock_name", "stock_code", "sector", "signal_type", "confidence", "evidence",
                "source_url", "mode",
            )
        }
        ok, response, retryable = deliver(outbound, self.trading_base_url, self.web_key)
        if ok:
            self.state.mark(event_id, "delivered", response)
            return "delivered"
        if retryable:
            self.state.mark_failure(event_id, response)
            return "delivery_failed"
        self.state.mark(event_id, "delivery_rejected", response)
        return "delivery_rejected"

    def run_once(self, *, bootstrap_existing: bool = False) -> dict[str, int]:
        if self.state.get_meta("initialized") is None:
            baseline = 0 if bootstrap_existing else self.archive.max_article_id(self.author_id)
            watermark = "1970-01-01T00:00:00+00:00" if bootstrap_existing else now_iso()
            self.state.initialize(last_article_id=baseline, last_scan_at=watermark)
            if not bootstrap_existing:
                return {
                    "articles": 0, "events": 0, "delivered": 0, "duplicates": 0,
                    "retried": 0, "retry_delivered": 0,
                }

        after_id = int(self.state.get_meta("last_article_id") or 0)
        updated_since = self.state.get_meta("last_scan_at") or "1970-01-01T00:00:00+00:00"
        scan_started = now_iso()
        articles = self.archive.fetch(self.author_id, after_id, updated_since)
        counts = {
            "articles": len(articles), "events": 0, "delivered": 0,
            "duplicates": 0, "retried": 0, "retry_delivered": 0,
        }
        max_id = after_id
        for article in articles:
            max_id = max(max_id, int(article["article_id"]))
            for parsed in self.parser.parse_all(article=article, mode=self.mode):
                signal = parsed.as_dict()
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

        # 신규 글 체크포인트를 먼저 확정한 뒤, 만기가 된 실패 건만 작은 배치로
        # 재시도한다. API blackhole backlog가 신규 글 감지를 막지 않게 한다.
        for row in self.state.pending(limit=10):
            payload = json.loads(row["payload_json"])
            status = self._send_event(row["id"], payload)
            counts["retried"] += 1
            if status == "delivered":
                counts["delivered"] += 1
                counts["retry_delivered"] += 1
                self._notify(
                    payload,
                    "재시도 관심종목 등록 성공 · Paper Runner 감시 대기 · 실전 주문 비활성",
                )
        return counts

    def run_loop(self, poll_seconds: int) -> None:
        while True:
            try:
                print(json.dumps(self.run_once(), ensure_ascii=False))
            except Exception as exc:
                # 일시 DB 잠금/읽기 실패로 상주 프로세스가 죽지 않는다. 체크포인트는
                # 성공한 run_once 끝에서만 이동하므로 다음 주기에 그대로 재시도한다.
                print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
            time.sleep(max(1, poll_seconds))
