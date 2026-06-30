# 기계 간 작업 동기화 규칙 (PC ↔ 노트북)

> **목적:** PC와 노트북에서 같은 작업을 모르고 따로 구현해 **충돌(divergence)** 나는 걸 막는다.
> 실제로 2026-06-27 `daily_archive` 기능이 양쪽에서 평행 구현돼 충돌이 났다 (아래 "사례" 참고).
> **이 문서는 양쪽 기계에 동일하게 둔다.** 작업 시작 전에 먼저 읽고, 끝나면 갱신한다.

**최종 갱신:** 2026-06-30 (노트북: retrieve→rerank 통합 완성) · 2026-06-27 (PC: §6 데이터 지침 추가) / **기준 브랜치:** `agent/rag-ingest-boundary`

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
- **노트북엔 `data/qdrant/`(≈600MB)만 복사한다. `archive.db`(16GB)는 옮기지 않는다.** 노트북이 하는 일(검색·리랭킹·eval)은 qdrant 인덱스만 필요하고, 청크 본문이 qdrant payload에 들어있어 `archive.db`를 안 거친다. `archive.db`는 수집/색인용이고 그건 PC 전담(§1).
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

### 진행 예정 (다음 작업 = "리랭킹 eval 실측")
1. **eval 실측** — "합성 쿼리 20개 중 10개 검색 실패 → 리랭킹 후 몇 개로 줄었나" 측정. **PC의 qdrant 인덱스가 노트북에 있어야 가능** (현재 Google Drive 미연결로 대기 — 연결되면 인덱스 받아 즉시 측정).
   - 코드는 다 됨: `retrieve_then_rerank` + `make_qdrant_search_fn`에 실제 qdrant client만 물리면 됨.

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

> 노트북에서 Claude Code로 작업할 때, "전체 DB를 옮겨야 하나?" 같은 데이터 복사 질문은 아래 결론을 그대로 따른다. (PC 측에서 2026-06-27 점검·확정한 논리)

**결론: 노트북엔 `data/qdrant/`(≈600MB)만 복사. `archive.db`(16GB)는 절대 옮기지 않는다.**

**왜 archive.db(16GB)는 불필요한가**
1. 노트북이 하는 일 = 검색·리랭킹·eval. 이건 **qdrant 인덱스만** 있으면 된다.
2. **청크 본문이 qdrant payload 안에 저장**돼 있어, 답변·리랭킹·eval이 `archive.db`를 거치지 않는다.
3. `archive.db`는 **수집/색인할 때만** 필요 → 그건 PC 전담(§1, "수집은 PC에서만").
4. 16GB를 양쪽에 두면 데이터 사본이 둘이 되어 **어긋남(divergence)** 위험 (§3 원칙 위반).

**복사 방법**
- PC에서 `data/qdrant/` 폴더를 압축 → 클라우드/USB → 노트북 같은 경로 `data/qdrant/`에 푼다.
- 노트북에선 **읽기 전용**으로만 사용. 노트북에서 수집·색인·`--execute` 임베딩 금지.
- PC가 재색인하면 노트북 사본은 오래된 스냅샷 → 필요 시 다시 복사.

**환경 주의 (테스트)**
- focused 테스트는 **시스템 pytest**로 돌므로, 테스트가 import하는 패키지(`numpy`/`qdrant_client`/`voyageai` 등)가 **시스템 Python에도** 설치돼 있어야 한다.
- PC에선 `voyageai` 누락으로 `test_rag_rerank`가 실패 → 시스템 Python에 `pip install voyageai`로 해결. 노트북도 같은 증상이면 동일 조치.
- 실행은 `.venv\Scripts\python.exe`(Python 3.12) 기준. venv와 시스템 Python은 분리돼 있다.
