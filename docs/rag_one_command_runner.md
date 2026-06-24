# RAG One-Command Verify Runner

복잡한 명령을 여러 번 치지 않고 **명령 한 번으로 RAG 파이프라인을 검증**하기 위한 러너다.

스크립트: `scripts/run_rag_verify.ps1`

## Purpose

`run_rag_verify.ps1`는 다음을 한 번에 실행한다:

1. End-to-end runtime smoke (068) — `scripts/run_rag_end_to_end_runtime_smoke.py`, synthetic fixture로 061~067 연결 검증
2. Focused RAG test suite — `scripts/run_rag_focused_tests.py`

프로젝트 `.venv` Python(3.12)을 자동으로 사용하므로, 시스템 `python`(3.14, 의존성 없음)으로 잘못 실행되어 실패하는 문제를 피한다.

## Usage

```powershell
# smoke + focused suite 전체 검증
.\scripts\run_rag_verify.ps1

# smoke만 빠르게
.\scripts\run_rag_verify.ps1 -SmokeOnly

# work-dir 지정 + 산출물 유지
.\scripts\run_rag_verify.ps1 -WorkDir .tmp/rag_e2e_runtime_smoke_manual -KeepArtifacts

# 도움말만 출력
.\scripts\run_rag_verify.ps1 -Help
```

옵션:

- `-SmokeOnly` — focused suite를 건너뛰고 smoke만 실행한다.
- `-KeepArtifacts` — smoke에 `--keep-artifacts`를 전달해 work-dir을 비우지 않고 재사용한다.
- `-WorkDir <path>` — smoke work-dir. 기본값 `.tmp/rag_e2e_runtime_smoke_verify`. smoke 안전 규칙상 `.tmp/rag_e2e_runtime_smoke*` 형태의 임시 경로여야 한다.
- `-Help` — 도움말만 출력하고 아무것도 실행하지 않는다.

## Output

각 단계 결과와 함께 마지막에 요약을 출력한다:

```
RAG Verify Summary
smoke result: PASS
focused suite result: PASS
RAG_VERIFY_RESULT=PASS
```

어느 단계든 실패하면 `RAG_VERIFY_RESULT=FAIL`과 0이 아닌 종료코드를 반환한다.

## Boundary

이 러너는 **검증 전용(verification only)**이다.

- synthetic fixture와 임시 work-dir 산출물만 사용한다.
- production RAG 지식 파이프라인(060~068을 `agent_reports/`에 대해 실제 실행)을 **실행하거나 변형하지 않는다.**
- 사람 검토 게이트(062 promotion, 066 approved_for_registry, 067 preview)를 **건너뛰지 않는다.** 실제 운영 흐름은 사람이 단계별로 진행하며, 그 절차는 `docs/rag_agent_operator_runbook.md`를 따른다.
- Trading Bot 파일, `data/`, `.env`, `archive.db`를 건드리지 않는다.

즉 운영(operator) 파이프라인의 자동 실행기가 아니라, 파이프라인이 깨지지 않았는지 빠르게 확인하는 검증기다.

## Related

- 운영 절차 전체: `docs/rag_agent_operator_runbook.md`
- smoke 상세: `docs/rag_end_to_end_runtime_smoke.md`
