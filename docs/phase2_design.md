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
