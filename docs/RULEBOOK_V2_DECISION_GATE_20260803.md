# Rulebook v2 다음 의사결정 게이트 — 2026-08-03

## 현재 판단

Rulebook v2의 12개 규칙 문구나 근거를 이번 검색 점수만으로 수정하지 않는다. Archive 원문 검증은
36/36 통과했고, 라이브 평가의 미회수 3건은 규칙 오류가 아니라 strict evidence retrieval의 한계와
동의 근거 중복 문제로 분리됐다.

A등급 4개 규칙의 Trading Bot 연구 계약은 준비됐지만 Trading Bot 백테스트 결과는 아직 없다.
따라서 규칙 상태는 전부 `research_hypothesis_unvalidated`를 유지한다.

## main 병합 후보

하나의 리뷰 단위로 다음을 묶을 수 있다.

1. 기존 Rulebook v2 PDF·구조화 규칙·원문 검증 산출물 (`edfee47`).
2. A등급 4개 규칙의 연구 전용 JSONL 계약과 인계 문서.
3. 12규칙 24문항 gold fixture, 생성기, 검증·진단 도구와 테스트.
4. 2026-08-03 production RAG 실측 보고서와 실패 분류.

병합은 실거래 적용이나 Trading Bot 연결 승인이 아니다. 연구 자산과 재현 기준선을 main에 보존하는
결정일 뿐이다.

## Git 게이트

- 현재 작업 브랜치: `agent/rag-trading-research-contract-20260803`
- 현재 기준 커밋: `edfee4754b3a40fe53e494b43ed2f9a4e6d7aea9`
- 확인 시점 `origin/main`: `2df7479ae18aa615e8e3047f40b759d8945c0527`
- 분기: main 고유 1, 현재 HEAD 고유 1. `origin/main`은 현재 브랜치의 조상이 아니다.
- 현재 변경은 아직 커밋·푸시하지 않았다.

오너가 커밋·푸시를 승인하면 작업 브랜치에서만 커밋한다. 이후 최신 main과 분기 상태를 다시 확인하고,
충돌 없는 rebase 또는 동등한 검토 가능한 통합 절차를 거친 뒤 전체 검증을 재실행한다. main 직접 커밋,
force push, 자동 병합은 금지한다.

## 병합 전 필수 검증

1. 현재 추가 테스트와 관련 기존 RAG 평가 테스트 통과.
2. 전체 suite를 `PYTHONUTF8=1`로 실행해 실제 passed 수와 rc 보고.
3. JSONL 생성기를 두 번 실행해 내용이 동일한지 확인.
4. `git diff --check`와 시크릿 패턴 검사 통과.
5. 독립 코드리뷰에서 소유권·실거래 금지·통계 누수·결과 과장 여부 확인.
6. 최신 main 반영 후 `HANDOFF.md` 최상단 기록을 실제 Git 상태에 맞게 갱신.

## 병합과 분리할 후속 연구

- GM-R01 최신성/핵심문구 query variant 연구.
- GM-R11 evidence-role coverage 또는 caveat 전용 검색 연구.
- GM-R02 동의 근거 `article_id` 396, 8471, 3144의 Rulebook 보조 근거 편입 검토.
- Trading Bot이 반환하는 `trading_rule_research_result`를 받은 뒤 규칙별 retain/reject 판정.

위 연구는 별도 브랜치에서 수행하며 현재 기준선 병합을 위해 결과를 좋게 만들 목적으로 fixture를 바꾸지
않는다.
