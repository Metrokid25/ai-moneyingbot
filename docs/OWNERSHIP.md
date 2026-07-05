# 데이터 소유권 · 접근 경계 계약 (OWNERSHIP)

> **이 문서는 계약이다.** ai-moneyingbot(랙봇)·archive봇·trading-bot 세 주체가 공유하는 데이터의
> 소유·읽기·쓰기 경계를 정의한다. 위반 시 인덱스 어긋남·DB 손상·병행구현 충돌이 발생한다.
> **이 문서는 rag repo와 trading-bot repo에 동일 사본으로 둔다.** 한쪽을 고치면 다른 쪽도 맞춘다.
>
> **최초 작성:** 2026-07-05 · RAG봇 담당 / **기준 브랜치:** `agent/rag-ingest-boundary`

---

## 0. 대원칙

- **repo는 통합하지 않는다.** rag와 trading-bot은 별도 repo다.
- **연동은 코드 import가 아니라 API / JSONL 계약 경계로만** 한다.
- **교차키(cross-key)는 `article_id`** 다. 모든 봇은 이 키로 같은 글을 가리킨다.

---

## 1. 데이터 소유권 3분할

| 데이터 도메인 | 자산 | **쓰기 소유자 (유일)** | 읽기 허용 | 위치 |
|---|---|---|---|---|
| **원본 코퍼스** | `archive.db`(원본), `mentor.db`(전체 본문 SQLite) | **archive봇** | 랙봇(읽기전용) | archive봇 기계, PC only |
| **파생 인덱스** | Qdrant 벡터인덱스(임베딩·청크) | **랙봇** | 랙봇(자기 소비) | rag repo `data/qdrant/` |
| **트레이딩 상태** | 포지션 / 체결 / 주문 로그 / OHLCV 캐시 | **trading-bot** | trading-bot only | trading-bot repo |

> 요약: **원본 텍스트 = archive봇**, **검색 인덱스 = 랙봇**, **매매 상태 = trading-bot**.

---

## 2. 절대 규칙 (위반 금지)

1. **데이터 소유권.** archive봇만 `archive.db`/`mentor.db`에 쓴다. 랙봇은 코퍼스를 **읽기전용**으로만 접근하고 자기 Qdrant 인덱스에만 쓴다. **어떤 봇도 다른 봇 소유의 DB에 쓰지 않는다.**
2. **트레이딩 데이터 격리.** 랙봇·archive봇은 trading-bot 소유 데이터(포지션/체결/주문/OHLCV)를 **읽지도 쓰지도 않는다.**
3. **사람 승인 후 커밋/푸시.** auto-merge/auto-push 금지.
4. **검증 출력은 액면 그대로.** 출력이 오면 가설로 추측하지 말고 실제 출력을 먼저 읽는다.

---

## 3. 연동 경계 (rag ↔ trading-bot)

- trading-bot은 랙봇의 내부 코드(`src/`)를 **직접 import 하지 않는다.**
- 연동은 **검색 API 계약** 또는 **JSONL 산출물**로만 한다. (계약 초안은 별도 문서 — 구현은 오너 승인 후.)
- 계약 응답의 최소 필드: `article_id`(교차키), `title`, `본문 발췌`, `score`, `date`.
- trading-bot의 매매 룰(R1~R12) 근거·개정·신규 발굴은 전부 이 코퍼스에서 나오며, 그 통로는 위 계약 경계다.

---

## 4. 갱신 규칙

- 소유 경계·규칙을 바꾸려면 **두 repo의 OWNERSHIP.md를 함께** 고치고, 오너 승인 후 각각 커밋한다.
- archive봇이 코퍼스를 재생성하면 랙봇/trading-bot의 사본은 낡는다 → 재생성 시 버전 스탬프를 남긴다(운영 규약은 MACHINE_SYNC.md).
