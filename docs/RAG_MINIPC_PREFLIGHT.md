# RAG 미니PC 인수인계·배포 전 사전점검

> **정본 목적:** 새 RAG 담당자는 채팅 프롬프트를 복사하지 말고 저장소를 동기화한 뒤 이 문서부터 따른다.
> 이 단계는 **읽기 전용 상태 확인**이다. PM이 별도로 "RAG 미니PC 배포 승인"이라고 지시하기 전에는
> 코드 갱신, 데이터 이관, `.env` 변경, 작업 스케줄 등록·실행을 하지 않는다.

## 1. 시작 원칙

- RAG 전용 checkout에서만 확인한다. Archive 운영 checkout과 섞지 않는다.
- dirty worktree에서 `pull`, `reset`, `checkout`, `clean`, `stash`를 실행하지 않는다.
- `scripts/_step3_verify_v2.py`가 보이면 소유 미확인 WIP이므로 수정·삭제·스테이징하지 않는다.
- 시크릿은 존재 여부만 확인하고 값은 출력하지 않는다.
- `archive.db`는 RAG에서 읽기 전용이다. trading-bot 저장소와 데이터는 범위 밖이다.

## 2. Git 상태 확인

RAG checkout에서 아래 명령만 실행한다.

```powershell
git fetch origin
git status --short --branch
git worktree list --porcelain
git log origin/main -3 --oneline --decorate
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count origin/main...HEAD
```

판정:

- tracked modified 또는 untracked 파일이 있으면 **중단 후 그대로 보고**한다.
- `HEAD != origin/main`이면 임의로 pull/rebase하지 말고 branch, ahead/behind와 함께 보고한다.
- 깨끗한 운영 checkout을 `main`으로 갱신하라는 PM 승인이 따로 있을 때만 `git pull --ff-only`를 사용한다.
- 현재 변경이 이미 `origin/main`에 있는지는 `git log origin/main --oneline -- <파일>`로 먼저 확인한다.

## 3. 미니PC 운영 상태 확인

```powershell
Get-ScheduledTask -TaskName "RAG-IncrementalIndex" -ErrorAction SilentlyContinue
Get-ScheduledTaskInfo -TaskName "RAG-IncrementalIndex" -ErrorAction SilentlyContinue |
  Select-Object LastRunTime, LastTaskResult

$archiveDb = "C:\projects\naver_cafe_archive\data\archive.db"
$ragRoot = "C:\projects\ai_moneyingbot_rag_agent"
$qdrant = Join-Path $ragRoot "data\qdrant"
$manifest = Join-Path $ragRoot "data\rag_index_manifest.jsonl"

@($archiveDb, $qdrant, $manifest) | ForEach-Object {
  [PSCustomObject]@{ Path = $_; Exists = Test-Path -LiteralPath $_ }
}
```

`.env`는 값 대신 필수 키 설정 여부만 확인한다.

```powershell
$envPath = "C:\projects\ai_moneyingbot_rag_agent\.env"
$requiredKeys = @(
  "VOYAGE_API_KEY",
  "RAG_TELEGRAM_BOT_TOKEN",
  "RAG_TELEGRAM_CHAT_ID"
)
$envText = if (Test-Path -LiteralPath $envPath) {
  Get-Content -LiteralPath $envPath -Raw
} else {
  ""
}
foreach ($key in $requiredKeys) {
  $isSet = $envText -match "(?m)^\s*$([regex]::Escape($key))\s*=\s*\S.*$"
  [PSCustomObject]@{ Key = $key; Configured = $isSet }
}
```

## 4. 읽기 전용 자산 안전 게이트

다음 조건을 모두 만족할 때만 실행한다.

- checkout이 안전 게이트를 포함한 최신 승인 commit이다.
- archive DB, Qdrant, manifest가 모두 존재한다.
- 어떤 RAG/Archive 프로세스도 해당 Qdrant 스냅샷을 쓰는 중이 아니다.

```powershell
cd C:\projects\ai_moneyingbot_rag_agent
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe scripts\check_rag_deploy_assets.py `
  --db-path "C:\projects\naver_cafe_archive\data\archive.db"
Write-Output "asset_guard_rc=$LASTEXITCODE"
```

PASS 기준:

- `status = PASS`
- `write_performed = false`
- `archive_db.sqlite_query_only = true`
- collection=`goodmorning_chunks`, vector size=`1024`, distance=`Cosine`
- Qdrant point 수와 manifest unique ID 수가 같음
- `point_ids_match_baseline = true`
- 결과코드 `0`

하나라도 다르면 배포 준비 실패다. 파일을 자동 복구하거나 구형 seed로 바꾸지 말고 출력 그대로 보고한다.

## 5. 오너에게 보낼 실측 보고 형식

```text
[RAG 미니PC 사전점검]
- 기계명/checkout 경로:
- branch/HEAD:
- origin/main:
- ahead/behind:
- tracked modified/untracked:
- archive.db 존재:
- Qdrant 존재:
- manifest 존재:
- .env 필수 3키 설정 여부(값 금지):
- RAG-IncrementalIndex 등록 여부:
- LastRunTime/LastTaskResult:
- 자산 안전 게이트: PASS/FAIL/미실행, rc:
- 배포·스케줄·데이터·시크릿 변경: 없음
- 다음 승인 요청:
```

명령과 실제 출력의 핵심을 함께 붙인다. 테스트 수와 결과코드는 추정하지 않는다.

## 6. PM이 배포를 승인한 뒤

사전점검 보고를 받은 PM이 배포 commit/tag를 확정하고 명시적으로 승인한 뒤에만
[`DEPLOY_MINIPC.md`](DEPLOY_MINIPC.md)를 처음부터 따른다.

순서는 반드시 다음과 같다.

1. 승인된 commit/tag로 깨끗한 RAG checkout 갱신
2. 동일 스냅샷의 Qdrant+manifest 한 쌍 이관
3. 자산 안전 게이트 PASS
4. `--dry-run --no-telegram`
5. 스케줄 등록
6. 수동 1회 실행
7. 텔레그램 수신과 `LastTaskResult=0` 실증
8. `HANDOFF.md` 맨 위에 명령·출력·결과코드를 기록하고 작업 브랜치로 반영

기존 태그 `deploy-baseline-20260705`는 과거 기준점이다. 최신 `main`을 배포할지 새 배포 태그를 만들지는
PM이 정하며, 담당자가 임의로 태그를 생성·이동하지 않는다.
