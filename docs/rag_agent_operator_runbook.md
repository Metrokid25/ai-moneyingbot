# RAG Agent Operator Runbook

운영자가 RAG Agent 지식 파이프라인(060~068)을 **실제로 어떤 순서로, 어떤 명령으로** 실행하는지 정리한 운영 문서다.

이 문서는 코드 구현 가이드가 아니라 운영 절차서다. 각 단계의 상세 설계는 단계별 문서를 참고한다:

- 060: `docs/rag_autonomous_learning_loop.md`
- 061: `docs/rag_research_memory_store.md`
- 062: `docs/rag_memory_promotion_gate.md`
- 063: `docs/rag_approved_memory_export_preview.md`
- 064: `docs/rag_approved_memory_rule_candidate_draft.md`
- 065: `docs/rag_rule_candidate_schema.md`
- 066: `docs/rag_approved_rule_candidate_registry.md`
- 067: `docs/rag_trading_export_preview.md`
- 068: `docs/rag_end_to_end_runtime_smoke.md`

## Scope and Boundaries

이 파이프라인은 "연구 → 기억 → 승인 → 룰 후보 → Registry → Trading handoff preview"까지만 수행하는 RAG 내부 지식관리 시스템이다.

다음은 절대 하지 않는다:

- Trading Bot 파일 생성/수정/연동, Archive Bot 파일 수정
- 실제 주문/매매 신호 생성 (`buy`, `sell`, `entry`, `exit`, `position`, `order`, `signal export`)
- live trading integration
- 외부 웹검색 기반 rule 생성, 외부 시황 판단
- `.env`, `archive.db`, `data/`, raw data, crawler 산출물 변경

산출물은 `agent_reports/`, `docs/`, `tests/`, `scripts/` 및 RAG 관련 JSON/JSONL/preview/registry/memory store에만 쓴다.

067의 Trading handoff preview는 실제 export가 아니다. 사람 검토용 preview일 뿐이며, Trading Bot input 파일이 아니고, rule export가 아니고, trading signal이 아니다.

## Prerequisites

- Windows + PowerShell 기준. README의 설치 절차로 `.venv`가 준비되어 있어야 한다.
- 명령은 activate 없이 `.\.venv\Scripts\python.exe`로 직접 호출한다.
- 작업 브랜치는 `agent/rag-` 로 시작해야 한다. `main`/`master`에서 자동 commit/push는 금지된다.
- 운영 산출물의 기본 위치는 `agent_reports/`이다.
  - Memory store: `agent_reports/rag_research_memory_store.jsonl`
  - Registry: `agent_reports/rag_rule_candidate_registry.jsonl`

## Pipeline at a Glance

실행 순서는 아래와 같다. 굵게 표시된 단계는 **사람 검토 게이트(human review gate)**로, 사람이 결정을 내리기 전에는 다음 단계로 진행하지 않는다.

1. 060 Research learning loop → 학습 후보(JSON) + answer(JSONL) 생성
2. 061 Memory store update → `rag_research_memory_store.jsonl`에 `pending` 기록 추가
3. **062 Promotion gate** → 사람이 `approved` / `rejected` 결정
4. 063 Approved memory export preview → 승인된 기억의 preview JSON/MD
5. 064 Rule candidate draft → `draft_needs_human_review` 상태의 draft JSON/MD
6. 065 Schema validation → 동결된 `rag_rule_candidate_draft` 스키마 검증
7. **066 Registry** → 사람이 draft를 `approved_for_registry`로 표시한 것만 등록
8. **067 Trading export preview** → `preview_needs_human_review` 상태의 handoff preview
9. 068 End-to-end runtime smoke → 061~067 연결을 synthetic fixture로 검증

## Step-by-Step

### Step 060 — Research learning loop

연구 검색·답변·학습 루프를 돌려 다음 단계 입력(학습 후보 + answer)을 만든다.

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_research_learning_loop.py
```

- 산출물: `agent_reports/`에 learning-loop JSON과 answer JSONL.
- 무인 반복이 필요하면: `.\scripts\run_rag_autonomous_loop.ps1`
- DB-only: 외부 웹검색·현재 시황·일반 경제지식·Naver Cafe 접근·archive 쓰기·Trading Bot rule 변경을 사용하지 않는다.

### Step 061 — Memory store update

학습 루프 산출물을 RAG research memory store에 적재한다. 새 기록은 `pending` 상태로 들어간다.

```powershell
.\.venv\Scripts\python.exe scripts\update_rag_research_memory_store.py --learning-loop-file <learning_loop.json>
```

- `--answer-file <answers.jsonl>`로 answer 소스를 추가할 수 있다.
- 기본 출력: `agent_reports/rag_research_memory_store.jsonl` (`--out-file`로 변경 가능).
- 먼저 점검만 하려면 `--dry-run`.

### Step 062 — Promotion gate (human review gate)

먼저 검토 프롬프트를 만든다.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_rag_memory_promotion_review.py
```

사람이 검토 후, 각 기억에 대해 상태를 적용한다.

```powershell
.\.venv\Scripts\python.exe scripts\update_rag_memory_promotion_status.py --memory-id <memory_id> --status approved --reviewer <name> --note "<reason>"
```

- `--status`는 `approved` / `rejected` / `pending` 중 하나.
- `<memory_id>`는 memory store JSONL의 `memory_id` 값이다.
- 승인된 기억만 다음 단계로 흐른다.

### Step 063 — Approved memory export preview

승인된 기억으로 preview를 만든다.

```powershell
.\.venv\Scripts\python.exe scripts\preview_rag_approved_memory_export.py
```

- 기본 입력: `agent_reports/rag_research_memory_store.jsonl`, 기본 출력: `agent_reports/` (JSON + MD).
- 승인된 기억이 0건이면 후속 단계가 비어 있게 되므로 062를 먼저 확인한다.

### Step 064 — Rule candidate draft

approved memory preview에서 RAG 내부 rule candidate draft를 생성한다.

```powershell
.\.venv\Scripts\python.exe scripts\draft_rag_approved_memory_rule_candidates.py
```

- `--preview-file`을 생략하면 `agent_reports/`의 **최신 preview**를 자동 선택한다. 특정 파일을 쓰려면 `--preview-file <approved_memory_preview.json>`.
- 생성된 draft 후보의 상태는 `draft_needs_human_review`이다 (아직 등록 대상 아님).

### Step 065 — Schema validation

동결된 `rag_rule_candidate_draft` (schema_version 1) 스키마로 draft를 검증한다.

```powershell
.\.venv\Scripts\python.exe scripts\validate_rag_rule_candidate_drafts.py --draft-file <rule_candidate_draft.json>
```

- `--format json`으로 기계 판독용 결과를 받을 수 있다.
- 검증 실패 시 등록(066)으로 진행하지 않는다.

### Step 066 — Registry (human review gate)

등록은 사람이 명시적으로 승인한 후보만 받는다. registry updater는 draft 후보 중 `draft_status` 값이 **`approved_for_registry`** 인 것만 등록한다.

1. 사람이 검토 후, 승인하기로 한 draft 후보의 `draft_status`를 `approved_for_registry`로 표시한다.
   - 이 표시를 자동으로 해주는 운영 스크립트는 없다. draft JSON에서 해당 후보 상태를 직접 편집한다. (068 smoke만 테스트 목적으로 이 단계를 프로그램적으로 수행한다.)
2. registry를 갱신한다.

```powershell
.\.venv\Scripts\python.exe scripts\update_rag_rule_candidate_registry.py --draft-file <approved_draft.json>
```

- `--draft-file`을 생략하면 최신 draft를 자동 선택한다.
- 기본 registry: `agent_reports/rag_rule_candidate_registry.jsonl`.
- 등록된 항목 상태는 `registered_needs_final_review`이다.
- 중복은 stable hash 기반 `registry_id`로 자동 방지된다. `approved_for_registry`가 아닌 후보는 "skipped not approved"로 집계된다.

### Step 067 — Trading export preview (human review gate)

registry에서 Trading handoff preview를 만든다. **이것은 실제 export가 아니다.**

```powershell
.\.venv\Scripts\python.exe scripts\preview_rag_trading_rule_export.py
```

- 기본 입력: `agent_reports/rag_rule_candidate_registry.jsonl`, 기본 출력: `agent_reports/` (JSON + MD).
- 기본 status 필터는 `registered_needs_final_review`이다.
- 생성된 preview 상태는 `preview_needs_human_review`이며, Trading Bot으로 자동 전달되지 않는다.
- Boundary: this is not a real export, not a Trading Bot input file, not a rule export, and not a trading signal.

### Step 068 — End-to-end runtime smoke

061~067 연결을 synthetic fixture로 검증한다. production 파일은 건드리지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_end_to_end_runtime_smoke.py --work-dir .tmp/rag_e2e_runtime_smoke_manual
```

- 안전한 임시 work-dir만 허용된다. repository root와 `agent_reports`, `data`, `scripts`, `tests`, `docs`, `src`, `.git`, `.venv`는 거부된다.
- 실패 시 work-dir의 smoke summary JSON에서 `failed_step`을 확인한다.

## Verification

작업 후에는 focused 테스트 스위트로 검증한다. 이것은 전체 pytest를 기본으로 호출하지 않고, RAG 관련 명령 `--help`와 핵심 RAG 테스트만 빠르게 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts\run_rag_focused_tests.py
```

전체 흐름의 연결성만 빠르게 확인하려면 068 smoke를 단독으로 실행한다.

## Error Handling

단계별 흔한 실패와 대응:

- 061 입력 누락: `--learning-loop-file` 경로가 060 산출물을 가리키는지 확인한다.
- 063 preview가 0건: 062에서 `approved`된 기억이 있는지 확인한다. 승인이 없으면 draft도 비어 있다.
- 064가 의도와 다른 preview 사용: `--preview-file`을 명시한다 (생략 시 최신 파일 자동 선택).
- 065 검증 실패: draft 스키마(`rag_rule_candidate_draft`, schema_version 1)를 벗어난 필드를 수정한 뒤 다시 검증한다. 통과 전 등록 금지.
- 066 "skipped not approved": 해당 후보의 `draft_status`가 `approved_for_registry`인지 확인한다. 등록은 사람이 승인한 후보만 받는다.
- 068 smoke 실패: smoke summary JSON의 `failed_step`을 보고, work-dir이 안전한 `.tmp/rag_e2e_runtime_smoke*` 경로인지 확인한다.
- 권한/실행정책 오류: README대로 activate 없이 `.\.venv\Scripts\python.exe`를 직접 호출한다.

## Publishing

빌더/리뷰어 절차를 따른다: 구현 → 테스트 → focused suite → review request → reviewer PASS 확인 → commit → push.

- PASS 없이 commit 금지. FAIL이면 수정 후 재리뷰.
- `git add .` 금지. 변경 파일만 개별 스테이징한다.
- `main`/`master` 자동 commit/push 금지. 작업 브랜치(`agent/rag-...`)에서만 진행한다.
- pass-gated 자동 발행이 필요하면 `.\scripts\run_rag_agent_pipeline.ps1 -CommitOnPass -PushOnPass`를 사용한다. 이 러너는 REVIEW_RESULT=PASS와 publish 안전 게이트 통과 후에만 발행한다.

## Quick Reference

```powershell
# 060 research learning loop
.\.venv\Scripts\python.exe scripts\run_rag_research_learning_loop.py
# 061 memory store
.\.venv\Scripts\python.exe scripts\update_rag_research_memory_store.py --learning-loop-file <learning_loop.json>
# 062 promotion gate (human)
.\.venv\Scripts\python.exe scripts\prepare_rag_memory_promotion_review.py
.\.venv\Scripts\python.exe scripts\update_rag_memory_promotion_status.py --memory-id <id> --status approved --reviewer <name>
# 063 approved memory preview
.\.venv\Scripts\python.exe scripts\preview_rag_approved_memory_export.py
# 064 rule candidate draft
.\.venv\Scripts\python.exe scripts\draft_rag_approved_memory_rule_candidates.py
# 065 schema validation
.\.venv\Scripts\python.exe scripts\validate_rag_rule_candidate_drafts.py --draft-file <draft.json>
# 066 registry (human marks approved_for_registry first)
.\.venv\Scripts\python.exe scripts\update_rag_rule_candidate_registry.py --draft-file <approved_draft.json>
# 067 trading export preview (not a real export)
.\.venv\Scripts\python.exe scripts\preview_rag_trading_rule_export.py
# 068 end-to-end runtime smoke
.\.venv\Scripts\python.exe scripts\run_rag_end_to_end_runtime_smoke.py --work-dir .tmp/rag_e2e_runtime_smoke_manual
# verification
.\.venv\Scripts\python.exe scripts\run_rag_focused_tests.py
```
