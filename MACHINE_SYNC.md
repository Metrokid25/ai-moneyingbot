# 기계 간 작업 동기화 규칙 (PC ↔ 노트북)

> **목적:** PC와 노트북에서 같은 작업을 모르고 따로 구현해 **충돌(divergence)** 나는 걸 막는다.
> 실제로 2026-06-27 `daily_archive` 기능이 양쪽에서 평행 구현돼 충돌이 났다 (아래 "사례" 참고).
> **이 문서는 양쪽 기계에 동일하게 둔다.** 작업 시작 전에 먼저 읽고, 끝나면 갱신한다.

**최종 갱신:** 2026-06-30 (PC: mentor.db 코퍼스 DB 노트북 이관 결정) · 2026-06-30 (PC: recall 실측 — rerank가 recall@1 0.40→0.80) · 2026-06-30 (PC: eval gold셋 40개 생성) / **기준 브랜치:** `agent/rag-ingest-boundary`

---

## 1. 역할 분담 (가장 중요)

| 기계 | 담당 | 안 하는 것 |
|---|---|---|
| **PC** | 아카이브 봇 **운영** (수집·임베딩·인덱싱), 데이터 보유 (`data/qdrant`, `archive.db` 약 42k건) | RAG 검색 알고리즘 신규 개발은 노트북과 겹치지 않게 |
| **노트북** | RAG **코드 개발** (검색 품질·리랭킹·eval), 읽기 전용 검증 | 실제 수집 실행 금지, 데이터에 쓰기 금지 |

**원칙:** 운영·데이터 = PC / 코드 개발 = 노트북. **데이터는 노트북에서 읽기 전용**으로만 쓴다(인덱스 어긋남 방지).

---

## 2. 충돌 방지 규칙 (작업 시작 전 체크리스트)

1. **시작 전 항상 동기화:** `git fetch origin` 후 `main`과 작업 브랜치 최신 상태 확인.
2. **재구현 금지:** 만들려는 기능이 **이미 `main`에 있는지** 먼저 확인.
   ```
   git log origin/main --oneline -- <대상파일>
   ```
   (오늘 충돌 원인: 브랜치가 stale이라 `main`의 `daily_archive` 완성본을 못 보고 다시 구현)
3. **같은 파일 동시 편집 금지:** 한 파일을 양쪽 기계에서 같은 시기에 건드리지 않는다.
4. **작업 브랜치 규칙:** RAG 작업은 `agent/rag-` 브랜치에서. `main`/`master`에 직접 commit/push 금지.
5. **끝나면 즉시 푸시 + 이 문서 갱신** (§4 "현재 상태"를 최신으로).
6. **task 큐(`agent_tasks/`)를 맹신하지 말 것:** 브랜치가 뒤처져 있으면 done 작업이 pending으로 남아있을 수 있다. 항상 `main`과 대조.

---

## 3. 데이터 동기화 (`data/`, `archive.db`)

- `data/`, `archive.db`, `data/qdrant/`는 **gitignore** — git으로 안 넘어간다. 기계별 로컬.
- 실제 코퍼스(약 42k건 본문 + qdrant 인덱스)는 **PC에만** 있음. 노트북엔 없음.
- **노트북엔 `data/qdrant/`(≈600MB) + `data/mentor.db`(≈170MB)를 복사한다. `archive.db`(16GB)는 옮기지 않는다.**
  - `data/qdrant/` = 의미검색(리랭킹·eval)용.
  - `data/mentor.db` = 전 글 42,947건 **전체 본문(clean_text) + 메타** 담은 단일 SQLite(LIKE + 트라이그램 FTS). 트레이딩봇용 코퍼스 마이닝/키워드검색·원문열람용. `scripts/build_mentor_db.py`로 `normalized_articles.jsonl`에서 생성 (2026-06-30 결정, §6 참고).
  - `archive.db`(16GB)의 추가분은 대부분 `raw_html`(수집 원본 마크업)이라 판단·검증에 안 쓰인다 → 옮기지 않는다.
- `embeddings_phase2.npy`도 노트북엔 불필요 — qdrant 적재용일 뿐, 질의엔 `data/qdrant/` 폴더만 있으면 됨.
- 복사한 인덱스는 노트북에서 **읽기 전용**으로만. (수집은 PC에서만 → 양쪽 인덱스 어긋남 방지. PC가 재색인하면 노트북 사본은 오래된 스냅샷이 되니 가끔 다시 복사.)

---

## 4. 현재 상태 (2026-06-27 기준)

### 완료
- **아카이브 봇: 완성** — `main`의 `3420185 "Wire bounded daily archive execution"`.
  `scripts/daily_archive.py`의 `--execute` 수집(limit/page-limit/delay 상한, `--collect-body`까지) 포함.
  → **이 기능은 건드리지 말 것. 이미 done.**
- **리랭킹 모듈: 완성** — 브랜치 `agent/rag-ingest-boundary` (`5ea34fb`, `f27d7f7`).
  `src/rag_rerank.py` = Voyage `rerank-2`로 검색 후보 재정렬. 단위테스트 15개. 독립 리뷰 통과.
- **검색 통합(retrieve → rerank): 완성** — 브랜치 (`bf36f59`, `36bbb07`).
  `src/rag_retrieve_rerank.py` = qdrant 과다인출(fetch_k) → `rag_rerank` → top_k. qdrant·Voyage 둘 다 주입 가능, fixture 테스트 15개. 독립 리뷰 통과. **이로써 리랭킹 "코드" 부분은 끝.**
- 기타: stale 테스트 수정(`f2653d9`), 노트북 RAG 개발 환경 세팅(venv·키).
- **mentor.db 코퍼스 DB 빌더: 완성 (PC, 2026-06-30)** — `scripts/build_mentor_db.py`.
  `normalized_articles.jsonl`(42,947건 전체 clean_text) → `data/mentor.db`(단일 SQLite, LIKE + 트라이그램 FTS5, ≈170MB).
  트레이딩봇 작업 시 노트북이 전 글을 키워드검색·원문열람하는 용도. qdrant(의미검색)와 병행. **db 파일은 gitignore → 수동 이관**(§3·§6).
- **eval gold셋: 완성 (PC, 2026-06-30)** — `tests/fixtures/rag_eval_questions_corpus.jsonl` (40문).
  생성기 `scripts/build_rag_eval_gold.py` = qdrant 인덱스(50,583청크) 전수에서 article당 1청크 표본추출 →
  gpt-4o-mini가 각 청크의 정답 질문 생성 → `expected_chunk_ids`/`expected_article_ids`에 실제 청크 id 기입.
  point-id 정렬 + `temperature=0,seed=0`으로 동일 인덱스에선 대체로 재현됨(바이트 보장은 아님).
  문서지칭형/근접중복/일반상식형 거부 필터 적용, 독립 코드리뷰 2회 통과.
  - **소프트 스폿(알 것):** 보편 사실 청크에서 나온 1~2문항(예: 인플레 타겟 2%)은 동일 주제 다른 청크도
    정답일 수 있어, 정답 청크가 top-k 밖이어도 검색기 잘못이 아닐 수 있음. recall은 chunk_id 기준이라 측정 자체는 유효.
- **recall 실측 러너 + 첫 측정: 완성 (PC, 2026-06-30)** — `scripts/evaluate_rag_recall_gold.py`.
  gold셋 `expected_chunk_ids`를 정답으로, 기존 `embed_query`+`make_qdrant_search_fn`+`retrieve_then_rerank`만 조합(재구현 없음).
  dense top-k vs over-fetch(fetch_k=50)→rerank를 같은 depth=10에서 recall@1/5/10·MRR@10으로 비교. 리포트는 `reports/`(gitignore).
  - **첫 실측 (gold 40문, voyage-3-large + rerank-2):**
    | 지표 | dense | +rerank |
    |---|---|---|
    | recall@1 | 0.400 | **0.800** |
    | recall@5 | 0.725 | **0.975** |
    | recall@10 | 0.800 | **0.975** |
    | MRR@10 | 0.539 | **0.881** |
    → **리랭킹이 recall@1을 2배로.** dense가 top10에서 놓친 8개 중 7개를 rerank가 복구. 양쪽 다 놓친 건 corpus-011 1개(gold 소프트스폿).
  - **노트북 주의:** 이 러너는 이미 done. **재구현 금지(§2-2).** 합성 20쿼리(`docs/rag_phase1_diagnosis.md`) 기반 실측을 따로 하고 싶으면 이 러너에 `--gold` 다른 파일로 주거나 별도 입력 어댑터만 추가.

### 진행 예정 (다음 작업 = "리랭킹 eval 실측") — 막힌 것 없음, 바로 가능
1. **eval 실측** — "합성 쿼리 20개 중 10개 검색 실패 → 리랭킹 후 몇 개로 줄었나" 측정.
   - **전제 모두 충족:** qdrant 인덱스(`goodmorning_chunks`, **50,583 청크**, 1024-dim, payload에 `text` 있음) + 리랭킹 코드 + Voyage 키.
   - 데이터: 노트북엔 2026-06-30 `data/qdrant/`(≈600MB) 복사·검증 완료. **PC엔 원본 인덱스가 이미 있어 PC에서 즉시 실행 가능.**
   - **할 일:** 기존 eval 자산(합성 쿼리 20개 + 정답 article_id — `docs/rag_phase1_diagnosis.md` 표)으로 **baseline(dense) vs `retrieve_then_rerank`** 순위 비교 스크립트 작성 → Voyage로 쿼리 임베딩 + rerank → 복구된 쿼리 수 집계.
   - **코드 진입점:** `src/rag_retrieve_rerank.py`의 `retrieve_then_rerank` + `make_qdrant_search_fn`(실제 qdrant client 주입).
2. ~~id 기반 recall@k / MRR 러너~~ → **완료 (위 §4 완료 참고, `evaluate_rag_recall_gold.py`).** 다음 후보:
   - **소프트스폿 보강:** corpus-011처럼 양쪽 다 놓치는 해석형 문항을 gold셋에서 교체(생성기 재실행, `--count` 늘려 거른 뒤 선별).
   - **fetch_k 스윕:** rerank의 fetch_k(현 50)를 25/100으로 바꿔 recall/지연·비용 트레이드오프 측정.
   - **합성 20쿼리 실측:** `docs/rag_phase1_diagnosis.md` 자산을 같은 러너 형식(`expected_chunk_ids`)으로 변환해 교차검증.

### 알려진 구조 이슈
- 브랜치 `agent/rag-ingest-boundary`가 `main`보다 **약 114커밋 앞섬(미병합)**. 이 큰 격차가 stale·충돌의 근본 원인.
  → 언젠가 리뷰 후 `main` 병합 필요(큰 결정). 그 전까지는 §2 규칙으로 충돌 관리.

---

## 5. 오늘 발생한 충돌 사례 (교훈)

- 노트북에서 `agent_tasks/pending/001-real-daily-archive-wiring.md`가 "할 일"로 남아 있어 `daily_archive --execute`를 새로 구현함(`7162be3`, `a91bd11`).
- 그런데 **PC/`main`엔 같은 기능이 5/29에 이미 완성**돼 있었음(`3420185`). 브랜치가 stale이라 못 봤던 것.
- 게다가 방향도 틀렸음: 노트북 버전은 `index_tail`의 **끝페이지(가장 오래된 글)**를 수집 → daily 신규 글엔 부적합. `main`은 **page 1(최신)**부터 수집 → 올바름.
- **조치:** 노트북 구현 폐기, `main` 완성본 채택(`692e4a7`).
- **교훈:** §2-2 (재구현 전 `main` 확인), §2-6 (task 큐 맹신 금지).

---

## 6. 노트북 Claude Code 지침 (데이터 동기화)

> 노트북에서 Claude Code로 작업할 때, "전체 DB를 옮겨야 하나?" 같은 데이터 복사 질문은 아래 결론을 그대로 따른다. (2026-06-30 갱신 — 트레이딩봇 작업을 위해 mentor.db 추가)

**결론: 노트북엔 `data/qdrant/`(≈600MB) + `data/mentor.db`(≈170MB)를 복사. `archive.db`(16GB)는 절대 옮기지 않는다.**

**왜 이 두 개면 충분하고 archive.db(16GB)는 불필요한가**
1. 노트북이 하는 일 = 검색·리랭킹·eval **+ 트레이딩봇용 코퍼스 마이닝**.
2. 검색·리랭킹·eval = **qdrant만** 있으면 된다(청크 본문이 qdrant payload에 있음).
3. 트레이딩봇 작업(스승님 글을 근거로 매수타점·매도규칙 판단) = **전 글 본문**이 필요한데, 그 **읽을 수 있는 텍스트(clean_text) 전체가 `mentor.db`(170MB)에 다 들어있다.** 42,947건 전부, 잘림 없음.
4. Claude는 애초에 DB를 통째로 읽지 못한다(컨텍스트 한계) → 항상 **검색해서 관련 글만** 읽는다. 그래서 필요한 건 "검색 가능한 전체 텍스트"이고, 그게 mentor.db(키워드/FTS) + qdrant(의미검색)다.
5. `archive.db`(16GB)의 추가분은 대부분 **`raw_html`**(수집 원본 마크업)이라 판단에 안 쓰인다. clean_text와 내용은 같은데 용량만 100배 → 옮길 이유 없음.
6. 16GB를 양쪽에 두면 사본이 둘이 되어 **어긋남(divergence)** 위험도 커진다(§3 원칙 위반).

**mentor.db 사용법(노트북)**
- 키워드/부분문자열: `SELECT article_id,title,posted_at FROM articles WHERE clean_text LIKE '%손절%';`
- 랭킹 전문검색(3글자↑): `SELECT a.article_id,a.title FROM articles_fts f JOIN articles a ON a.article_id=f.rowid WHERE articles_fts MATCH '분할매수' ORDER BY rank;`
- 원문 읽기: `SELECT clean_text FROM articles WHERE article_id=28832;`
- PC가 재수집하면 스냅샷이 낡음 → `scripts/build_mentor_db.py` 재실행 후 재이관. **읽기 전용**.

**복사 방법**
- PC에서 `data/qdrant/` 폴더를 압축 → 클라우드/USB → 노트북 같은 경로 `data/qdrant/`에 푼다.
- 노트북에선 **읽기 전용**으로만 사용. 노트북에서 수집·색인·`--execute` 임베딩 금지.
- PC가 재색인하면 노트북 사본은 오래된 스냅샷 → 필요 시 다시 복사.

**환경 주의 (테스트)**
- focused 테스트는 **시스템 pytest**로 돌므로, 테스트가 import하는 패키지(`numpy`/`qdrant_client`/`voyageai` 등)가 **시스템 Python에도** 설치돼 있어야 한다.
- PC에선 `voyageai` 누락으로 `test_rag_rerank`가 실패 → 시스템 Python에 `pip install voyageai`로 해결. 노트북도 같은 증상이면 동일 조치.
- 실행은 `.venv\Scripts\python.exe`(Python 3.12) 기준. venv와 시스템 Python은 분리돼 있다.
