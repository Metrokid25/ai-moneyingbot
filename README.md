# naver-cafe-archive

개인 학습 목적의 네이버 카페 글 아카이브 도구.

- 사용자가 직접 브라우저에서 로그인 후 열람 가능한 글만 저장한다.
- 로그인 우회 · 캡차 우회 · 프록시 기능 없음.
- 차단 화면 감지 시 자동 중단 후 상태를 기록한다.

---

## 설치

```bash
cd C:\projects\naver_cafe_archive

# 가상환경 생성 (선택)
python -m venv .venv
.venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# Playwright 브라우저 바이너리 설치
playwright install chromium
```

## 환경 변수 설정

```bash
copy .env.example .env
# 필요하면 .env 편집
```

---

## 1단계: 글 1개 저장

```bash
python src/main.py "https://cafe.naver.com/카페명/글번호"
```

1. Chromium 창이 열린다.
2. 필요하면 네이버 로그인을 직접 진행한다.
3. 스크립트가 자동으로 글을 파싱하고 `data/archive.db`에 저장한다.

같은 `article_id`로 재실행하면 `[SKIP]`으로 건너뛴다.

**출력 예시**

```
[INFO] article_id: 123456
[INFO] 브라우저를 열어 페이지를 로드합니다 ...
[OK] 저장 완료
  title     : 투자 일지 3월
  posted_at : 2024.03.15. 09:30
  chars     : 1842
```

---

## 2단계: 굿머닝 작성글 목록 인덱싱

글 본문은 수집하지 않고 목록 정보(article_id, title, url, author, posted_at)만 저장한다.

```bash
python src/indexer.py "https://cafe.naver.com/멤버글목록URL" --start 2826 --end 1
```

- `--start`: 시작 페이지 번호 (오래된 글부터 수집하려면 큰 숫자)
- `--end`: 끝 페이지 번호
- 페이지 이동마다 3~5초 랜덤 대기

**이어서 실행**: 중단 후 재실행하면 이미 저장된 `article_id`는 자동 SKIP하고 이어서 진행한다.

**목록 URL 확인 방법**:
1. 네이버 카페에서 굿머닝 프로필 → 작성글 탭을 연다.
2. 브라우저 주소창의 URL을 복사한다.
3. `page=N` 파라미터가 있는 URL이면 그대로 사용한다.

**출력 예시**

```
[INFO] 인덱싱 시작: 2826페이지 (2826 → 1)

[PAGE 2826] https://cafe.naver.com/...&page=2826
  저장: 15개  스킵: 0개  (누적: 15개)
  [3.7초 대기]

[PAGE 2825] https://cafe.naver.com/...&page=2825
  저장: 15개  스킵: 0개  (누적: 30개)
```

**파싱 실패 시**: `debug/page_{번호}.html` 과 `debug/page_{번호}.png` 에 저장된다.

---

## DB 확인

```bash
# 전체 현황
sqlite3 data/archive.db "SELECT status, COUNT(*) FROM articles GROUP BY status;"

# 최근 저장된 글
sqlite3 data/archive.db "SELECT article_id, title, posted_at, status FROM articles ORDER BY saved_at DESC LIMIT 20;"

# 인덱싱된 글 수
sqlite3 data/archive.db "SELECT COUNT(*) FROM articles WHERE status='INDEXED';"
```

---

## 파일 구조

```
C:\projects\naver_cafe_archive\
  README.md
  requirements.txt
  .env.example
  src/
    main.py       # 글 1개 저장 진입점
    indexer.py    # 목록 인덱서
    db.py         # SQLite CRUD + 마이그레이션
    browser.py    # Playwright 세션 관리
    parser.py     # HTML 파싱 (글 본문 + 목록)
    models.py     # Article 데이터클래스
    config.py     # 환경 변수 로드
  data/
    archive.db    # 실행 시 자동 생성
  debug/
    page_N.html   # 파싱 실패 시 저장
    page_N.png    # 파싱 실패 시 스크린샷
```

## articles 테이블 스키마

| 컬럼 | 타입 | 설명 |
|---|---|---|
| article_id | TEXT PK | 글 번호 |
| title | TEXT | 제목 |
| url | TEXT | 글 URL |
| author | TEXT | 작성자 (목록 인덱싱 시 "굿머닝" 고정) |
| posted_at | TEXT | 작성일 |
| raw_html | TEXT | 본문 원본 HTML (본문 수집 후 채워짐) |
| clean_text | TEXT | 본문 텍스트 (본문 수집 후 채워짐) |
| source_page | INTEGER | 수집된 목록 페이지 번호 |
| status | TEXT | OK / INDEXED / FAILED |
| error_reason | TEXT | 실패 사유 |
| saved_at | TEXT | 저장 시각 (UTC ISO) |

## status 코드

| status | 의미 |
|---|---|
| `INDEXED` | 목록에서 URL/제목만 수집됨 (본문 미수집) |
| `OK` | 본문까지 수집 완료 |
| `FAILED` | 수집 실패 |

## error_reason 코드

| error_reason | 원인 |
|---|---|
| `login_required` | 로그인 페이지로 리다이렉트됨 |
| `no_permission` | 카페 가입 필요 또는 비공개 글 |
| `captcha` | 자동입력 방지 화면 감지 |
| `age_verification` | 성인인증 / 본인확인 화면 감지 |
| `navigation_failed: ...` | 네트워크 오류 또는 타임아웃 |
| `frame_load_failed: ...` | iframe 로드 실패 |
