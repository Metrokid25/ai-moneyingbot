# Phase 2 설계 문서 — 본문 수집 (Body Collection)

작성일: 2026-04-26  
기준 HEAD: `557201d`  
상태: **검증 단계 설계 확정** / 배치 단계 미설계

---

## 섹션 1 — 개요

**Phase 2 목표**: 인덱싱된 ~42,000건 Article 메타데이터 각각에 대해 네이버 카페 본문(clean_text, raw_html)을 수집해 DB에 저장한다.

### 진행 2단계

| 단계 | 목표 | 진입 조건 |
|------|------|-----------|
| **검증 단계** | single-shot 진입점으로 단건 수집 확인 | 지금 바로 시작 |
| **배치 단계** | INDEXED 전체를 루프로 수집 | 검증 단계 종료 기준(섹션 7) 충족 후 별도 설계 |

**본 문서 범위**: 검증 단계 설계까지. 배치 단계(루프 구조, 세션 재생성 주기, 진행률 저장, rate limiting 등)는 검증 완료 후 별도 문서로 작성한다.

---

## 섹션 2 — 반영할 리뷰 항목 8건

self-review + Codex adversarial review에서 "Phase 2 설계 반영"으로 분류된 항목.

| ID | 출처 | 심각도 | 한 줄 요약 | 처리 위치 |
|----|------|--------|-----------|-----------|
| B-1 | self | HIGH | `get_articles_by_status()` 없어 INDEXED만 추출 불가 | `src/db.py` 신규 함수 |
| B-2 | self | HIGH | `upsert_article()`이 status 무조건 덮어씀 → 역주행 위험 | `src/db.py` CASE 가드 + `update_article_body()` 신규 |
| B-3 | self | HIGH | `fetch_page()` one-shot 패턴 = 매 호출마다 새 Chromium + 딜레이 없음 | `src/collector.py` 에서 세션 주입 구조로 해결 |
| A-1 | self | HIGH | networkidle silent-pass 후 빈 본문 silent 저장 | `collect_body()` 내 `clean_text` 길이 검증 → BODY_EMPTY |
| C-1 | self | HIGH | `saved_at` 항상 갱신 → 최초 저장 시각 소실 | DB 스키마 `updated_at` 분리 |
| D-1 | self | HIGH | Phase 2 배치에 `_sleep()` 없을 경우 딜레이 0 | 배치 루프에서만 `_sleep()` 호출 (단건 함수 내부에는 없음) |
| A-3 | self | MEDIUM | 로그인 3초 하드코딩 → 느린 환경에서 세션 미확립 | 검증 단계 영향 없음. 배치 설계 시 처리 (섹션 6) |
| B-4 | self | MEDIUM | 42K 장시간 실행 시 Chromium 메모리 누수 | 세션 재생성 주기 미결정 (섹션 8). 단건 함수 설계상 무관 |

---

## 섹션 3 — DB 변경사항

### 3-1. 신규 함수 (`src/db.py` 추가)

#### `get_article_by_id(article_id: str) -> Optional[Article]`

```python
# SELECT * FROM articles WHERE article_id = ?
# 본문 수집 시 단건 조회. 없으면 None 반환.
```

#### `get_articles_by_status(status: str, limit: Optional[int] = None) -> List[Article]`

```python
# SELECT * FROM articles WHERE status = ? ORDER BY article_id
# LIMIT ? (limit이 None이면 생략)
# 배치 단계에서 INDEXED 상태 글만 추출하기 위한 진입점.
```

#### `update_article_body(article_id: str, raw_html: str, clean_text: str, new_status: str) -> None`

```python
# UPDATE articles
#   SET raw_html = ?, clean_text = ?, status = ?, updated_at = ?
#   WHERE article_id = ?
# upsert_article()을 거치지 않고 본문/상태만 갱신.
# status 역주행(B-2) 차단: BODY_COLLECTED/BODY_BLOCKED 상태를
#   이 함수 호출자가 덮어쓰는 경우 ValueError raise.
```

---

### 3-2. status 값 체계 확정

| status | 의미 | 진입 조건 | 다음 단계 |
|--------|------|-----------|-----------|
| `INDEXED` | 메타데이터만 존재 | Phase 0/1 인덱싱 결과 | Phase 2 수집 대상 |
| `BODY_COLLECTED` | 본문 수집 성공 | `clean_text` 길이 ≥ MIN_BODY_LENGTH | 최종 완료 |
| `BODY_EMPTY` | 본문 수집 시도했으나 빈 결과 | `clean_text` 길이 < MIN_BODY_LENGTH | 재시도 대상 |
| `BODY_FAILED` | 네트워크/파싱 에러 | `goto()` / `parse_article()` 예외 | 재시도 대상 |
| `BODY_BLOCKED` | 차단/권한 문제 감지 | `login_required`, `no_permission`, `captcha` 등 | 사람이 확인 필요, 자동 재시도 X |
| ~~`OK`~~ | (deprecated) | `main.py` one-shot 잔재 | Phase 2에서 사용 안 함 |
| ~~`FAILED`~~ | (deprecated) | `main.py` one-shot 잔재 | Phase 2에서 사용 안 함 |

> `OK` / `FAILED`는 `main.py` one-shot 진입점의 잔재이며, Phase 2 이후로는 신규 레코드에 사용하지 않는다. 기존 레코드는 그대로 유지(마이그레이션 불필요).

---

### 3-3. `saved_at` / `updated_at` 분리 (C-1 대응)

#### 문제

현재 `upsert_article()`의 ON CONFLICT 절에 `saved_at = excluded.saved_at`이 포함되어, Article dataclass의 `saved_at`이 `datetime.now()`로 매번 재생성된다. 최초 INSERT 시각이 덮어씌워진다.

#### 변경 내용

**스키마 변경**:
```sql
ALTER TABLE articles ADD COLUMN updated_at TEXT;
```
`_migrate()` 안에서 `"updated_at" not in existing` 조건으로 추가.

**컬럼 의미 재정의**:
- `saved_at`: "최초 INSERT 시각" — ON CONFLICT 절에서 갱신하지 않음
- `updated_at`: "마지막 UPDATE 시각" — INSERT 시 `saved_at`과 동일 값으로 초기화, 이후 변경마다 갱신

**`upsert_article()` ON CONFLICT 절 변경**:
```sql
ON CONFLICT(article_id) DO UPDATE SET
    title        = excluded.title,
    url          = excluded.url,
    author       = excluded.author,
    posted_at    = excluded.posted_at,
    raw_html     = excluded.raw_html,
    clean_text   = excluded.clean_text,
    source_page  = excluded.source_page,
    status       = <CASE 가드 — 3-4 참조>,
    error_reason = excluded.error_reason,
    updated_at   = excluded.updated_at
    -- saved_at 제외: 최초 INSERT 시각 보존
```

**기존 INDEXED 41건 백필**:
```sql
UPDATE articles SET updated_at = saved_at WHERE updated_at IS NULL;
```
`init_db()` 내 `_migrate()` 완료 후 실행.

---

### 3-4. `upsert_article()` status 안전 가드 (B-2 대응)

ON CONFLICT 절의 status 갱신을 조건부로 변경:

```sql
status = CASE
    WHEN articles.status IN ('BODY_COLLECTED', 'BODY_BLOCKED')
        THEN articles.status   -- 완료/차단 확정 상태는 보존
    ELSE
        excluded.status        -- 그 외는 새 값으로 갱신
END
```

**의도**:
- `BODY_COLLECTED` / `BODY_BLOCKED`: 본문 수집 결과 확정 상태. 메타 재인덱싱이 와도 덮어쓰지 않음.
- `BODY_EMPTY` / `BODY_FAILED`: 재시도 가능 상태. 의도적 재시도 시 `INDEXED`로 리셋 허용.
- `INDEXED`: 초기 상태. 정상적으로 갱신됨.

---

## 섹션 4 — collector 구조 (`src/collector.py` 신규)

### 4-1. 책임

`src/collector.py`는 단건 본문 수집 함수 `collect_body()`를 제공한다.

- **검증 단계**: `src/collect_one.py`에서 single-shot으로 직접 호출
- **배치 단계**: 배치 루프에서 세션을 주입해 반복 호출 (배치 설계 시 추가)
- `BrowserSession`은 호출자가 주입하면 재사용, `None`이면 내부에서 생성 후 닫음

### 4-2. `collect_body()` 흐름

```
collect_body(article_id: str, session: Optional[BrowserSession] = None) -> str
```

```
1. db.get_article_by_id(article_id)
   └─ 없으면 ValueError("article_id not found")

2. 사전 체크
   └─ status in ('BODY_COLLECTED', 'BODY_BLOCKED')
      → 스킵, 현재 status 반환

3. 세션 준비
   └─ session is None → own_session = BrowserSession()
   └─ session 주입됨  → own_session = None (close 하지 않음)

4. session.goto(url) 호출
   ├─ err == "login_required"
   │   → db.update_article_body(article_id, "", "", "BODY_BLOCKED")
   │   → 반환 "BODY_BLOCKED"  (단발이므로 wait_for_login 호출 X)
   ├─ err == "next_error"
   │   → diagnostic HTML 저장 (debug/)
   │   → db.update_article_body(article_id, "", "", "BODY_FAILED")
   │   → 반환 "BODY_FAILED"
   ├─ err in ("no_permission", "captcha", "age_verification")
   │   → db.update_article_body(article_id, "", "", "BODY_BLOCKED")
   │   → 반환 "BODY_BLOCKED"
   └─ err == "navigation_failed"
       → db.update_article_body(article_id, "", "", "BODY_FAILED")
       → 반환 "BODY_FAILED"

5. session.get_frame_html() 호출
   └─ 실패 → BODY_FAILED

6. parse_article(html) → (title, posted_at, clean_text, raw_html)

7. clean_text 길이 검증 (A-1 대응)
   ├─ len(clean_text.strip()) < MIN_BODY_LENGTH (50자)
   │   → db.update_article_body(article_id, raw_html, clean_text, "BODY_EMPTY")
   │   → 반환 "BODY_EMPTY"
   └─ 충족
       → db.update_article_body(article_id, raw_html, clean_text, "BODY_COLLECTED")
       → 반환 "BODY_COLLECTED"

8. finally: own_session이 있으면 close()
```

### 4-3. `BrowserSession` fetch 메서드 (B-3 대응)

기존 `browser.py`의 `fetch_page(url)`는 매 호출마다 새 `BrowserSession`을 생성하고 닫으므로 배치에 사용 불가.

`collect_body()`는 기존 `BrowserSession` 인스턴스의 `goto()` + `get_frame_html()`을 직접 호출한다. 별도 `fetch_html()` 메서드 추가는 불필요 — 기존 두 메서드 조합으로 충분.

`fetch_page()`는 `main.py` one-shot 전용으로 유지 (건드리지 않음).

### 4-4. `_sleep()` 위치 (D-1 대응)

| 위치 | `_sleep()` 여부 | 이유 |
|------|----------------|------|
| `collect_body()` 내부 | **없음** | 단건 함수. 딜레이 책임은 호출자에게 있음 |
| 검증 단계 `collect_one.py` | **없음** | single-shot이므로 불필요 |
| 배치 단계 루프 (미구현) | **있음** | 매 article 처리 후 `_sleep(3~5s)` 호출 |

---

## 섹션 5 — 검증용 진입점 (single-shot)

### 5-1. `src/collect_one.py` 신규 파일

실행 방법:
```bash
python -m src.collect_one <article_id>
# 또는
cd src && python collect_one.py <article_id>
```

인터페이스:
```
argparse:
  positional: article_id (str)
  optional: --force  (BODY_COLLECTED 상태도 재수집)
```

출력 형식 (예시):
```
[collect_one] article_id: 53
─────────────────────────────────────────────
  title      : 항공주 주가를 결정하는 키워드는?
  url        : https://cafe.naver.com/...
  status     : INDEXED → BODY_COLLECTED
  body_len   : 2,341자
  preview    : 안녕하세요 굿머닝입니다. 오늘은 항공주 주...
  image_urls : 3개 (저장 안 함, 카운트만)
  elapsed    : 4.2초
─────────────────────────────────────────────
```

### 5-2. 첫 검증 대상

| 항목 | 값 |
|------|----|
| article_id | `53` |
| 제목 | 항공주 주가를 결정하는 키워드는? |
| 전제 조건 | PC에서 사용자 수동 로그인 완료 상태 |
| 실패 시 | `debug/diagnostic_*.html` 분석으로 원인 추적 |

---

## 섹션 6 — 검증 단계에서 미반영 항목

| 항목 | 이유 | 처리 시점 |
|------|------|-----------|
| **A-3** (로그인 3초 하드코딩) | 검증 단계는 사용자가 수동 로그인 + 엔터로 진행. `wait_for_login()`은 indexer에서만 사용. `collect_body()`는 login_required 시 즉시 BODY_BLOCKED 처리하므로 영향 없음. | 배치 단계 설계 시 처리 |
| **B-4** (세션 재생성 주기) | 단건 함수(`collect_body()`) 설계상 무관. 재생성 주기는 배치 루프 구조가 확정된 후 결정. | 배치 단계 설계 시 결정 |

---

## 섹션 7 — 검증 단계 종료 기준

다음 **4가지 모두** 충족 시 배치 단계 설계 진입:

1. **기본 수집 성공**: `article_id=53` 단건 → `BODY_COLLECTED` 성공, `clean_text` 한글 정상 인코딩
2. **본문 정합성 확인**: `clean_text` 길이 적절, 광고/스크립트 제거 확인, 이미지 URL 카운트 정상
3. **추가 샘플 성공**: 임의 4~5개 `article_id`에서 single-shot 성공률 확인
4. **에러 분기 재현**: `BODY_EMPTY` / `BODY_FAILED` / `BODY_BLOCKED` 중 최소 1개를 의도적으로 재현 (예: 로그인 풀린 상태에서 호출 → `BODY_BLOCKED` 확인)

---

## 섹션 8 — 비결정 항목 (검증 완료 후 별도 결정)

| 항목 | 현재 상태 | 결정 시점 |
|------|-----------|-----------|
| 세션 재생성 주기 (B-4) | 미결정 | 배치 설계 회의 |
| 배치 진입점 CLI 설계 | 미결정 | 검증 완료 후 |
| 진행률 저장 / 중단 후 재개 로직 | 미결정 | 배치 설계 회의 |
| 이미지/첨부 다운로드 정책 | 미결정 | 배치 설계 회의 |
| 일일 수집 상한 (rate limiting) | 미결정 | 배치 설계 회의 |
| `MIN_BODY_LENGTH` 임계값 (현재 50자 예시) | 검증 중 실측 후 확정 | 검증 2~3건 후 |

---

## 섹션 9 - Phase 2 메타데이터 스키마 결정

작성일: 2026-05-18

### 9-1. 현재 수집 완료 상태

`archive.db`는 read-only 모드로 확인했다.

| 항목 | 값 |
|------|----|
| articles | 42,756 |
| max_article_id | 169,913 |
| BODY_COLLECTED | 42,756 |
| INDEXED | 0 |
| BODY_FAILED | 0 |
| clean_text NULL | 0 |
| body_len = 0 | 2 |
| body_len 1~9자 | 1,005 |
| 신규 수집 article_id > 169461 | 121 |
| 신규 body_len 1~9자 | 4 |

현재 `articles` 테이블 컬럼은 다음과 같다.

```text
article_id, title, url, author, posted_at, raw_html, clean_text,
source_page, status, error_reason, saved_at, updated_at,
attempt_count, last_error_reason, last_attempt_at
```

`has_media` 컬럼은 현재 DB schema에 없다.

### 9-2. 스키마 결정

Phase 2 메타데이터 스키마는 **표준형 스키마 + 확장 필드 reserved** 방식으로 확정한다.

필수 메타데이터 필드는 다음과 같다.

| field | type | rule |
|-------|------|------|
| `article_id` | `int` | 원본 `articles.article_id` |
| `chunk_id` | `str` | `{article_id}:{chunk_index}` |
| `chunk_index` | `int` | 같은 article 안에서 0부터 시작 |
| `posted_at` | `str` | 원본 `articles.posted_at` 문자열 보존 |
| `year` | `int \| null` | 날짜형 `posted_at`에서만 파싱 |
| `month` | `int \| null` | 날짜형 `posted_at`에서만 파싱 |
| `title` | `str` | 원본 `articles.title` |
| `body_len` | `int` | `len(clean_text or "")` |
| `author` | `str \| null` | 원본 `articles.author` |
| `source` | `str` | 고정값 사용 |
| `status` | `str` | 원본 `articles.status` |

현재 `articles` 테이블에 `has_media` 컬럼이 없으므로 Phase 2 필수 필드에서 `has_media`는 제외한다. 추후 `raw_html` 기반 재파싱 또는 별도 media detection을 구현할 때 optional field로 추가할 수 있다.

### 9-3. reserved 확장 필드

아래 필드는 Phase 2 초기 인덱싱에서는 필수로 채우지 않고, 추후 검색 품질 개선 및 피드백 루프를 위해 reserved로 둔다.

| field | type |
|-------|------|
| `sector_tags` | `list[str]` |
| `asset_tags` | `list[str]` |
| `macro_tags` | `list[str]` |
| `signal_type` | `str \| null` |
| `market_phase` | `str \| null` |
| `risk_level` | `str \| null` |
| `feedback_score` | `float \| null` |
| `retrieved_count` | `int` |
| `last_retrieved_at` | `str \| null` |

### 9-4. `chunk_id` 규칙

권장 규칙:

```text
chunk_id = "{article_id}:{chunk_index}"
```

예:

```text
article_id=169913, chunk_index=0 -> chunk_id="169913:0"
```

### 9-5. `source` 규칙

현재 프로젝트의 source는 다음 고정값을 사용한다.

```text
source = "naver_cafe_119investment_goodmorning"
```

### 9-6. `posted_at` 처리 규칙

현재 DB에는 `posted_at`이 두 형태로 존재한다.

- 날짜형: `2026.05.15.`
- 당일 시간형: `11:47`

처리 원칙:

- 원본 `posted_at` 문자열은 그대로 보존한다.
- `year` / `month`는 날짜형 `posted_at`에서만 파싱한다.
- 시간형 `posted_at`은 수집일 기준 날짜 보정이 가능해지기 전까지 `year` / `month`를 `null`로 둘 수 있다.
- 잘못된 날짜 추측을 하지 않는다.

### 9-7. 짧은 본문 처리 원칙

현재 `body_len` 1~9자 글은 1,005건 존재하고, 신규 수집 121건 중 4건도 짧은 종목 메모형 글이다.

처리 원칙:

- 짧은 본문은 수집 오류로 단정하지 않는다.
- `title`과 `clean_text`가 짧더라도 실제 멘토님 메모일 수 있으므로 기본적으로 보존한다.
- Phase 2 인덱싱 시 짧은 글은 제외하지 않는다.
- 단, 검색 품질 평가에서 짧은 글의 노이즈 여부를 별도 추적한다.

### 9-8. 다음 결정 항목: 청킹 전략

아직 청킹 전략은 확정하지 않는다. 후보는 다음과 같다.

- 글 단위 1 chunk 기본
- 장문만 길이 기준으로 분할
- 제목 + 본문 결합 텍스트를 embedding text로 사용

---

## 섹션 10 - Phase 2 청킹 전략 결정

작성일: 2026-05-18

### 10-1. 결정 요약

Phase 2 청킹 전략은 **기본 article 단위 1 chunk + 장문만 분할** 방식으로 확정한다.

embedding 대상 텍스트는 다음 규칙으로 생성한다.

```text
embedding_text = title + "\n\n" + clean_text
```

기본 원칙:

- 기본은 article 단위 1 chunk로 저장한다.
- `embedding_text` 길이 1500자 미만은 1 chunk로 유지한다.
- 짧은 종목 메모형 글도 제외하지 않고 1 chunk로 보존한다.
- `embedding_text` 길이 1500자 이상만 분할 대상으로 삼는다.

장문 분할 원칙:

- 문단 기준 분할을 우선한다.
- 문단 기준 분할이 어려운 경우 1000~1200자 단위로 fallback 분할한다.
- overlap은 150~200자로 둔다.

### 10-2. chunk 식별 규칙

`chunk_index`는 article 안에서 0부터 시작한다.

```text
chunk_id = "{article_id}:{chunk_index}"
```

예:

```text
article_id=169913, chunk_index=0 -> chunk_id="169913:0"
```

### 10-3. 근거 데이터

직전 DB read-only 분석 결과는 다음과 같다.

| 항목 | 값 |
|------|----|
| 전체 articles | 42,756 |
| clean_text median | 130 |
| clean_text p75 | 374 |
| clean_text p90 | 1,075.5 |
| clean_text p95 | 1,963 |
| clean_text p99 | 4,235.45 |
| embedding_text median | 152 |
| embedding_text p90 | 1,096.5 |
| embedding_text p95 | 1,984.25 |
| embedding_text >= 1500 | 2,999건 |
| 후보 B 예상 chunk 수 | 약 50,131개 |
| 후보 A 대비 chunk 증가율 | 약 17.3% |

해석:

- 대부분의 글은 짧다. `clean_text` median은 130자이고 p75도 374자다.
- 장문은 소수지만 검색 품질에 영향을 줄 수 있다. `clean_text` p95는 1,963자, p99는 4,235.45자다.
- `embedding_text >= 1500`은 2,999건으로 전체의 일부이므로, 장문만 분할하면 비용 증가를 제한하면서 장문 검색 정확도를 개선할 수 있다.
- 후보 B의 예상 chunk 수는 약 50,131개로, 모든 글 1 chunk인 후보 A 대비 약 17.3% 증가에 그친다.

### 10-4. 후보 비교 요약

| 후보 | 전략 | 평가 | 결정 |
|------|------|------|------|
| A | 모든 글 1 chunk | 가장 단순하지만 장문 검색 정확도에 약점이 있다. | 미채택 |
| B | 기본 1 chunk + 장문만 분할 | 현재 데이터 분포에 가장 적합하다. 짧은 글 보존과 장문 검색 정확도의 균형이 좋다. | 채택 |
| C | 모든 글 고정 길이 분할 | 짧은 글이 많은 현재 데이터에는 과하다. chunk 수와 관리 복잡도가 불필요하게 늘어난다. | 미채택 |

### 10-5. 구현 시 주의사항

- 짧은 종목 메모형 글은 수집 오류로 단정하지 않는다.
- `title`이 짧은 본문을 보강하는 경우가 있으므로 embedding text에는 항상 `title`을 포함한다.
- 분할 후 metadata에는 같은 `article_id`, 원본 `posted_at`, `title`, `status`, `source`를 유지한다.
- Phase 2 구현 시 이 섹션은 청킹 로직의 기준 문서로 사용한다.

---

## 섹션 11 - Phase 2 벡터 DB 선택

작성일: 2026-05-18

### 11-1. 현재 요구사항

Phase 2 벡터 DB는 다음 조건을 기준으로 선택한다.

- 원본 DB `archive.db`는 보존용 source of truth로 유지한다.
- 임베딩 모델은 `voyage-3-large`, 벡터 차원은 1024차원이다.
- 청킹 후 예상 chunk 수는 약 50,131개다.
- 필수 metadata는 `article_id`, `chunk_id`, `chunk_index`, `posted_at`, `year`, `month`, `title`, `body_len`, `author`, `source`, `status`다.
- reserved metadata는 추후 필터링과 피드백 루프에 활용할 수 있어야 한다.
- 로컬 Windows 개발에서 시작하되, 추후 trading-bot과 분리된 검색 서버로 이관할 수 있어야 한다.
- 벡터 DB 파일은 재생성 가능한 산출물로 보고 git에 커밋하지 않는다.

참고한 공식 문서:

- Qdrant: local mode, Docker server, payload/filtering 문서
- Chroma: Python client, persistent client, HTTP/server client, metadata filtering 문서
- LanceDB: embedded local path, vector search, metadata filtering 문서

### 11-2. 후보 비교

| 기준 | Qdrant | Chroma | LanceDB |
|------|--------|--------|---------|
| 로컬 개발 편의성 | Python local mode 또는 Docker로 시작 가능 | PersistentClient로 매우 빠르게 시작 가능 | local path 기반 embedded 방식으로 시작 가능 |
| Windows 개발 환경 적합성 | Docker 또는 Python client local mode 선택 가능 | Python 로컬 개발이 단순함 | Python SDK 사용 가능. 로컬 파일 기반이라 단순함 |
| Python 연동 편의성 | 공식 `qdrant-client` 제공 | 공식 Python client 제공 | 공식 Python client 제공 |
| 1024차원 벡터 적합성 | collection 생성 시 vector size 지정 가능 | embedding/vector 저장 가능 | vector column 기반 저장 가능 |
| 약 50,000 chunk 규모 | 충분히 가벼운 규모 | 로컬 실험에는 충분한 규모 | embedded 파일 기반 처리에 적합한 규모 |
| metadata 필터링 | payload 기반 filtering과 payload index가 강점 | `where` metadata filter 제공 | SQL-like `where` filtering 제공 |
| trading-bot 연결 | 별도 검색 서버로 분리하기 좋음 | 빠른 로컬 연결은 쉽지만 운영 분리는 별도 server 구성 필요 | embedded 중심이면 bot 프로세스와 결합되기 쉬움 |
| 운영/Docker 이관 | Docker 서버와 Cloud 이관 경로가 명확함 | server-backed Chroma 구성이 가능함 | embedded 우선. Enterprise/remote 선택지는 있으나 현재 요구에는 부차적 |
| 백업/재생성 전략 | collection을 산출물로 보고 재생성하기 쉬움 | persistent directory를 산출물로 관리 가능 | Lance 파일 디렉토리를 산출물로 관리 가능 |
| 프로젝트 복잡도 대비 | 운영 이관까지 고려하면 적절함 | 실험에는 가장 단순하지만 장기 운영 기준으로는 한 단계 약함 | 컬럼형/파일 기반 장점은 있으나 현재 RAG 서버화 목표에는 우선순위 낮음 |

### 11-3. 최종 선택

최종 추천은 **Qdrant**다.

선택 이유:

- 약 50,000개 chunk 규모에서는 충분히 가볍다.
- 1024차원 `voyage-3-large` 벡터를 collection vector size로 명시해 저장하기 쉽다.
- payload 기반 metadata 저장과 filtering이 현재 Phase 2 schema와 잘 맞는다.
- `year`, `month`, `source`, `status`, `article_id`, 추후 `sector_tags`, `asset_tags`, `market_phase` 같은 필터 조건을 검색 API에서 직접 다루기 좋다.
- 로컬 개발은 Qdrant local mode 또는 Docker 방식으로 시작할 수 있다.
- 추후 trading-bot과 검색 서버를 분리할 때 Docker Qdrant 또는 원격 Qdrant로 이관하기 쉽다.
- vector DB를 재생성 가능한 산출물로 두고, 원본 `archive.db`와 청킹/임베딩 스크립트를 source of truth로 유지하는 현재 원칙과 맞다.

### 11-4. 보류한 후보와 이유

#### Chroma

Chroma는 빠른 로컬 실험과 Python 개발 편의성이 가장 큰 장점이다. PersistentClient로 로컬 디스크 저장을 쉽게 시작할 수 있고, metadata `where` filter도 제공한다.

다만 이 프로젝트는 Phase 2 이후 trading-bot과 분리된 검색 서버로 이관할 가능성이 높다. 장기 운영과 metadata filtering 중심 검색을 우선하면 Qdrant가 더 적합하므로 Chroma는 보조안으로 둔다.

보조안:

- 빠른 실험만 목표라면 Chroma도 가능하다.
- 장기 운영을 전제로 하는 Phase 2 기본 선택지는 Qdrant로 둔다.

#### LanceDB

LanceDB는 로컬 파일 기반 embedded DB와 컬럼형 포맷이 장점이다. vector search, full-text search, hybrid search, metadata filtering을 한 파일 기반 데이터셋 흐름 안에서 다루기 좋다.

다만 현재 프로젝트는 원본 `archive.db`를 별도로 보존하고, vector DB는 trading-bot 또는 검색 API가 붙을 수 있는 별도 검색 저장소로 둘 계획이다. 이 기준에서는 embedded/파일 중심 장점보다 Qdrant의 서버화와 payload filtering 장점이 더 중요하다.

따라서 LanceDB는 현재 우선순위에서 Qdrant/Chroma보다 낮게 둔다.

### 11-5. 저장 위치 원칙

- 벡터 DB 데이터는 `data/vector_db` 또는 `data/qdrant` 같은 `data` 하위 경로에 둔다.
- `data` 하위 파일은 git에 커밋하지 않는다.
- `.db`, `.npy`, vector DB storage, snapshot, 대용량 산출물은 커밋 대상에서 제외한다.
- collection 이름과 저장 경로는 Phase 2 구현 시 명시적으로 고정한다.

권장 초기 경로:

```text
data/qdrant
```

### 11-6. 재생성 원칙

벡터 DB는 source of truth가 아니라 재생성 가능한 산출물이다.

재생성 입력:

- `data/archive.db`
- Phase 2 청킹 코드
- `voyage-3-large` 임베딩 스크립트
- metadata schema 규칙
- chunk_id 규칙

재생성 원칙:

- `archive.db`에서 `BODY_COLLECTED` article을 읽는다.
- 확정된 청킹 전략으로 `embedding_text`와 chunk를 만든다.
- `voyage-3-large`로 1024차원 임베딩을 생성한다.
- Qdrant collection에 vector와 payload metadata를 다시 적재한다.
- 벡터 DB 파일 자체는 git에 올리지 않는다.

### 11-7. 아직 구현하지 않는 항목

이번 결정은 문서화까지만 포함한다. 아래 항목은 아직 구현하지 않는다.

- Qdrant 패키지 설치
- Qdrant Docker 실행
- collection 생성 코드
- chunk 생성 코드
- embedding 생성/업로드 코드
- vector DB 재생성 스크립트
- trading-bot 검색 API 연결

---

## 섹션 12 - Qdrant 실행 방식 결정

작성일: 2026-05-18

### 12-1. 초기 개발 실행 방식

초기 개발은 Qdrant Python client의 local path 방식으로 시작한다.

```python
QdrantClient(path="data/qdrant")
```

선택 이유:

- 현재 단계는 Windows 로컬 개발이다.
- 예상 chunk 수 약 50,131개는 local path 방식으로 검증하기에 충분히 작은 규모다.
- Docker 없이 Python 코드에서 바로 청킹/임베딩/검색 파이프라인을 실험할 수 있다.
- 서버 프로세스, 포트, 볼륨 관리를 도입하기 전에 검색 품질과 metadata schema를 먼저 검증할 수 있다.
- `archive.db`에서 벡터 DB를 재생성할 수 있으므로 local path 저장소는 산출물로 취급해도 된다.

### 12-2. 운영 이관 방식

trading-bot과 연결하거나 검색 서버를 분리하는 단계에서는 Docker Qdrant 또는 원격 Qdrant 서버로 이관한다.

이관을 쉽게 하기 위해 구현 시 Qdrant 접속 설정은 코드에 하드코딩하지 않고 설정값으로 분리한다. local path 방식과 server 방식은 같은 상위 인터페이스에서 교체 가능해야 한다.

### 12-3. Docker 방식 보류 이유

Docker Qdrant는 지금 당장 사용하지 않는다.

보류 이유:

- 현재 단계에서는 인프라 복잡도가 늘어난다.
- 포트, 볼륨, 서버 프로세스 관리가 추가된다.
- 아직 청킹/임베딩/검색 파이프라인 자체를 검증하기 전이다.
- local path 방식으로도 약 5만 chunk 규모의 초기 검색 품질 검증은 충분하다.

Docker Qdrant는 운영 이관 또는 trading-bot 분리 시점에 다시 선택한다.

### 12-4. 저장 경로 원칙

기본 로컬 저장 경로는 다음으로 둔다.

```text
data/qdrant
```

저장 원칙:

- `data/qdrant`는 git commit 금지 대상이다.
- `data/qdrant`는 산출물이며, `archive.db` + 청킹 코드 + 임베딩 코드 + 메타데이터 규칙으로 같은 collection을 다시 만들 수 있어야 한다.
- `.db`, `.npy`, Qdrant storage, snapshot, 기타 대용량 산출물은 git에 올리지 않는다.

### 12-5. 설정값 분리 원칙

Phase 2 구현 시 아래 값은 설정으로 분리한다.

```text
QDRANT_MODE=local
QDRANT_PATH=data/qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=goodmorning_chunks
VECTOR_SIZE=1024
DISTANCE=cosine
```

설정 의미:

- `QDRANT_MODE=local`: `QdrantClient(path=QDRANT_PATH)` 사용
- `QDRANT_MODE=server`: `QdrantClient(url=QDRANT_URL)` 사용
- `QDRANT_COLLECTION`: Phase 2 chunk collection 이름
- `VECTOR_SIZE`: `voyage-3-large` 임베딩 차원
- `DISTANCE`: cosine similarity 사용

### 12-6. 재생성 원칙

Qdrant local path 저장소는 원본이 아니라 산출물이다.

재생성 절차는 다음 입력으로 가능해야 한다.

- `data/archive.db`
- Phase 2 청킹 코드
- `voyage-3-large` 임베딩 코드
- metadata schema 규칙
- chunk_id 규칙
- Qdrant 설정값

재생성 시 기존 `data/qdrant`를 보존할지 삭제 후 재생성할지는 구현 단계에서 명시적인 CLI 옵션으로 분리한다.

### 12-7. 아직 구현하지 않는 항목

이번 결정은 문서화까지만 포함한다. 아래 항목은 아직 구현하지 않는다.

- `qdrant-client` 패키지 설치
- Qdrant collection 생성 코드
- Qdrant local path 초기화 코드
- Docker Qdrant 실행
- `.env` 또는 config 파일 변경
- chunk 생성 코드
- 임베딩 생성/업로드 코드
- 검색 API 또는 trading-bot 연결

---

## Section 13 - Phase 2 Qdrant Load Implementation Notes

Date: 2026-05-19

- Qdrant point IDs use deterministic UUIDs derived from `uuid.uuid5(POINT_ID_NAMESPACE, chunk_id)`.
- The original `chunk_id` remains in payload for traceability.
- The chunk `embedding_text` is stored in Qdrant payload as `text`.
- Real Qdrant collection creation and upsert require `--execute`.
- Existing collection recreation requires both `--execute` and `--recreate`.
- Default validation and `--dry-run` must not create `data/qdrant`.

---

## Section 14 - Phase 2 Qdrant Retrieval Sanity Check

Date: 2026-05-19

- Phase 2 Qdrant local storage was loaded at `data/qdrant`.
- Collection `goodmorning_chunks` contains 50,131 points.
- Retrieval sanity checks use `scripts/search_qdrant_phase2.py`.
- Search execution requires `--execute` because it calls Voyage query embedding.
- Dry-run checks collection status and query settings without calling Voyage.
- Query embeddings use `voyage-3-large` with 1024 dimensions.

---

## Section 15 - Phase 2 Retrieval Evaluation Report

Date: 2026-05-19

- Retrieval quality review uses `scripts/evaluate_retrieval_phase2.py`.
- The script runs 15 fixed Korean evaluation queries across macro, market, and sector themes.
- Results are written to `data/retrieval_eval_phase2.jsonl`.
- The report file is a generated data artifact and must not be committed.
- Real evaluation requires `--execute` because it calls Voyage query embedding.
- Existing report files are preserved unless `--overwrite --execute` is explicitly used.

---

## Section 16 - Phase 2 Answer Context Builder

Date: 2026-05-20

- The answer context builder prepares retrieved Qdrant chunks as grounded context for a later answer-generation step.
- It does not generate the final LLM answer.
- Input: a user question, `top_k`, output format, Qdrant local path, and collection name.
- Output: Markdown by default, or JSON with `question`, `top_k`, and ranked result records.
- Each result includes rank, score, chunk/article IDs, title, posted date, year/month, source, text snippet, and `empty_text`.
- `scripts/build_answer_context_phase2.py` calls Voyage query embedding only with `--execute`.
- `--dry-run` validates settings and collection status without Voyage API calls or output artifacts.
- Qdrant usage is read/search only against `data/qdrant` and `goodmorning_chunks`.
- Generated data artifacts under `data`, `.db`, `.npy`, Qdrant storage, snapshots, and context output samples must not be committed.

---

## Section 17 - Phase 2 Minimal Final Answer Generation

Date: 2026-05-21

- `src/rag_answering.py` adds the minimal prompt, LLM call, and final answer formatting layer.
- `scripts/answer_question_phase2.py` runs: user query -> Voyage query embedding -> Qdrant top_k search -> answer context -> Korean LLM answer -> sources.
- Output format is Markdown by default, or JSON with `query`, `answer`, `sources`, `model`, and `top_k`.
- `--execute` is required before any Voyage or LLM API call can happen.
- `--dry-run` checks settings and Qdrant collection status, then prints the execution plan without calling Voyage or the LLM.
- Qdrant usage is read/search only against the existing local collection. The answer script must not create, recreate, upsert, or delete Qdrant points.

Example commands:

```powershell
.\.venv\Scripts\python.exe scripts\answer_question_phase2.py --query "금리 인상 국면에서 주식시장은 어떻게 반응하는가" --dry-run
.\.venv\Scripts\python.exe scripts\answer_question_phase2.py --query "금리 인상 국면에서 주식시장은 어떻게 반응하는가" --top-k 5 --format markdown
.\.venv\Scripts\python.exe scripts\answer_question_phase2.py --query "금리 인상 국면에서 주식시장은 어떻게 반응하는가" --top-k 5 --format json --execute
```

Excluded from this minimal step:

- MMR
- dedup
- reranking
- score threshold
- snippet improvement
- trading-bot integration

Example commands:

```powershell
.\.venv\Scripts\python.exe scripts\build_answer_context_phase2.py --query "금리 인상 국면에서 주식시장은 어떻게 반응하는가" --dry-run
.\.venv\Scripts\python.exe scripts\build_answer_context_phase2.py --query "금리 인상 국면에서 주식시장은 어떻게 반응하는가" --execute
.\.venv\Scripts\python.exe scripts\build_answer_context_phase2.py --query "환율 상승과 외국인 수급" --execute --format json
.\.venv\Scripts\python.exe scripts\build_answer_context_phase2.py --query "반도체 업황과 삼성전자" --execute --out data/answer_context_sample.md
```
