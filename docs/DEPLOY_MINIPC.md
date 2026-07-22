# 미니PC 배포 — RAG 증분 색인 무인 운영 (DEPLOY_MINIPC.md)

> **범위:** RAG 봇의 **증분 색인 파이프라인**(archive.db 읽기 → 신규 청크 임베딩 → Qdrant 반영 → 텔레그램 통지)을
> 미니PC(Minimaite VM-P1M)에서 하루 1회 무인 실행하도록 세팅한다.
> **범위 밖:** 카페 글 **수집·로그인**은 Archive 봇 소관이다. archive.db를 채우는 건 Archive 봇의 배포 문서를 따른다.
> 이 문서는 그 archive.db를 **읽기 전용**으로 소비할 뿐이다 (docs/OWNERSHIP.md).
>
> **전제:** 미니PC는 운영 전용 — 코드 수정 금지, `git pull`로만 갱신. 상시 프로세스만 돈다.

---

## 인수인계 시작점 — 먼저 읽기 전용 사전점검

새 RAG 담당자는 채팅에서 받은 프롬프트를 기준으로 배포하지 않는다. 저장소를 `git fetch`한 뒤
[`RAG_MINIPC_PREFLIGHT.md`](RAG_MINIPC_PREFLIGHT.md)에 따라 Git/worktree/스케줄/자산 상태를
읽기 전용으로 실측해 오너에게 보고한다.

PM이 그 보고를 확인하고 **배포 commit/tag와 실제 배포를 명시 승인한 뒤에만** 아래 0단계부터 진행한다.
dirty worktree에서는 `pull`, `reset`, `checkout`, `clean`, `stash`로 상태를 바꾸지 않는다.

---

## 0. 준비물 체크리스트

- [ ] 미니PC에 Python **3.12** 설치 (`py -3.12 --version`으로 확인)
- [ ] Voyage API 키 (`VOYAGE_API_KEY`)
- [ ] RAG **전용** 텔레그램 봇 토큰 + 채널 id (@BotFather로 생성 — trading-bot과 별개)
- [ ] 외장 SSD/USB 또는 네트워크 공유 (대용량 데이터 이전용)
- [ ] Archive 봇이 미니PC에 배포되어 **archive.db 경로가 확정**돼 있을 것

---

## 1. 코드 가져오기

```powershell
cd C:\projects
git clone https://github.com/Metrokid25/ai-moneyingbot.git ai_moneyingbot_rag_agent
cd C:\projects\ai_moneyingbot_rag_agent
# 이 단계는 PM이 배포 commit/tag를 명시 승인한 뒤에만 실행한다.
git checkout main
git pull --ff-only
git log -1 --oneline --decorate
```

> `deploy-baseline-20260705`는 과거 기준점이다. 최신 main 또는 새 배포 태그 선택은 PM 결정이며,
> 담당자가 기존 태그를 현재 배포 승인으로 간주하거나 임의로 이동하지 않는다.

## 2. venv 생성 + 의존성 설치

```powershell
cd C:\projects\ai_moneyingbot_rag_agent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> RAG 색인 역할에는 **브라우저(playwright chromium)가 필요 없다.** 수집은 Archive 봇 몫이므로
> `playwright install chromium`은 생략해도 된다. (수집도 이 미니PC에서 돌린다면 Archive 봇 문서를 따라 설치.)

## 3. 환경변수(.env) 설정

```powershell
cd C:\projects\ai_moneyingbot_rag_agent
Copy-Item .env.example .env
notepad .env
```

`.env`에 채울 값:

```
VOYAGE_API_KEY=<voyage 키>
RAG_TELEGRAM_BOT_TOKEN=<RAG 전용 봇 토큰>
RAG_TELEGRAM_CHAT_ID=<통지 받을 채널/채팅 id>
```

## 4. 대용량 데이터 초기 이전 (git 제외 대상 — 수동 복사)

`data/`는 gitignore라 clone에 포함되지 않는다. 개발 기계(PC)에서 미니PC로 **직접 복사**한다.

**반드시 옮길 것 (RAG 소유):**

| 파일/폴더 | 크기 | 용도 |
|---|---|---|
| `data/qdrant/` | ≈600MB | 벡터 인덱스 (색인 대상) |
| `data/rag_index_manifest.jsonl` **또는** `data/embeddings_phase2_ids.npy` | 작음 | **색인 베이스라인** — 없으면 첫 실행이 5만 청크를 전부 신규로 보고 재임베딩(Voyage 대량 과금) |

```powershell
# (개발 PC에서) 압축
cd C:\projects\ai_moneyingbot_rag_agent
Compress-Archive -Path data\qdrant, data\rag_index_manifest.jsonl -DestinationPath $env:USERPROFILE\Desktop\rag_data.zip -Force

# (미니PC에서) 외장/네트워크로 받은 zip을 프로젝트 data\ 아래에 푼다
cd C:\projects\ai_moneyingbot_rag_agent
Expand-Archive -Path <복사한_rag_data.zip 경로> -DestinationPath data\ -Force
```

> `manifest`가 아직 없던 시점의 스냅샷이면 대신 `data\embeddings_phase2_ids.npy`를 옮긴다 (첫 실행이 이걸로 베이스라인을 1회 시드한다).
> **archive.db(16GB)는 이 문서 범위 밖** — Archive 봇 배포 문서대로 옮기고, 그 경로를 5단계 `-DbPath`에 넣는다.

### 4.1 배포 자산 안전 게이트 (읽기 전용·무과금)

스케줄 등록 전에 Qdrant와 매니페스트/seed가 같은 스냅샷인지 확인한다. 이 검사는
Qdrant를 클라이언트로 열지 않고 `meta.json`과 `storage.sqlite`를 SQLite `mode=ro`로만 읽으며,
Voyage·텔레그램을 호출하거나 어떤 파일도 쓰지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts\check_rag_deploy_assets.py `
  --db-path "C:\projects\naver_cafe_archive\data\archive.db"
```

정상 조건:

- `status = PASS`, `write_performed = false`
- collection = `goodmorning_chunks`, vector size = `1024`, distance = `Cosine`
- Qdrant `points_count` = 매니페스트(또는 seed) `unique_ids_count`
- 각 chunk_id의 deterministic UUID5와 실제 Qdrant point ID 집합이 완전히 일치 (`point_ids_match_baseline = true`)
- archive.db `sqlite_query_only = true`

매니페스트가 존재하면 그것이 권위값이다. 매니페스트가 손상됐을 때 구형 seed로 조용히
fallback하지 않고 실패한다. Qdrant/기준선 개수가 다르거나 둘 다 없으면 **배포 중단** 후
올바른 한 쌍을 다시 이관한다.

## 5. 스케줄 등록 (하루 1회, 장 마감 후)

archive.db 경로를 `-DbPath`로 지정한다 (Archive 봇이 배포한 실제 경로).

```powershell
cd C:\projects\ai_moneyingbot_rag_agent
.\scripts\register_rag_index_schedule.ps1 -DbPath "C:\projects\naver_cafe_archive\data\archive.db" -Time "16:30"
```

- 기본 태스크명 `RAG-IncrementalIndex`, 매일 16:30(로컬=KST) 실행.
- 재실행하면 기존 태스크를 덮어쓴다(idempotent).
- Qdrant 경로가 기본(`data/qdrant/`)과 다르면 `-QdrantPath`로 지정.
- 등록 스크립트는 4.1 안전 게이트를 다시 실행한다. 실패하면 태스크를 등록·덮어쓰기 전에 중단한다.
- 커스텀 기준선 경로는 `-ManifestPath` / `-SeedIdsPath`로 지정하며, 같은 경로가 예약 작업 래퍼에도 전달된다.

## 6. 동작 확인

```powershell
cd C:\projects\ai_moneyingbot_rag_agent
# (a) 등록 확인
Get-ScheduledTask -TaskName "RAG-IncrementalIndex"
# (b) 텔레그램 통지 없이 배선만 점검 (신규 감지만, 임베딩/적재 없음)
.\.venv\Scripts\python.exe scripts\run_rag_incremental_notify.py --db-path "C:\projects\naver_cafe_archive\data\archive.db" --dry-run --no-telegram
# (c) 실제 1회 수동 실행 → 텔레그램 수신 확인
Start-ScheduledTask -TaskName "RAG-IncrementalIndex"
# (d) 마지막 실행 결과 코드 확인 (0 = 성공)
Get-ScheduledTaskInfo -TaskName "RAG-IncrementalIndex" | Select-Object LastRunTime, LastTaskResult
```

정상이면 텔레그램에 `✅ RAG 증분색인 …` 또는 `신규 0건 (인덱스 최신)` 통지가 온다.
실패 시 `🔴 RAG 증분색인 실패 …` 통지에 사유가 담긴다.
dry-run은 `신규 N청크 감지 (미반영)`으로 출력되며 실제 임베딩·upsert·매니페스트 갱신은 없다.

---

## 트러블슈팅

- **태스크는 등록됐는데 안 뜬다 (`LastTaskResult` 0x2 / 로그온 실패):** S4U 실행에는 계정에
  **"Log on as a batch job"(배치 작업 로그온)** 권한이 필요하다. 표준 로컬 계정엔 없을 수 있다.
  `secpol.msc` → 로컬 정책 → 사용자 권한 할당 → "배치 작업으로 로그온"에 해당 계정 추가 후 재시도.
  (권한이 없으면 래퍼가 아예 안 떠서 **텔레그램 실패통지도 안 온다** — 배포 직후 6단계 (c)로 반드시 실증할 것.)
- **첫 실행이 오래 걸린다 / 2시간 제한에 걸린다:** 4단계에서 manifest(또는 seed ids)를 **반드시** 옮겨
  베이스라인을 잡아야 한다. 안 그러면 첫 실행이 5만 청크를 전부 신규로 보고 재임베딩하다 `-ExecutionTimeLimit`(2h)에
  걸려 중단될 수 있다. 정상 일일 델타는 수 분이다.
- **`deployment asset preflight failed` / count 또는 point ID set mismatch:** Qdrant와 manifest/seed가 서로 다른
  스냅샷이다. 실행·등록은 안전하게 차단된 상태다. 임의로 파일을 생성하거나 개수를 맞추지 말고,
  개발 PC에서 검증된 Qdrant+manifest 한 쌍을 다시 이관한 뒤 4.1을 재실행한다.
- **부팅 직후 실행돼 네트워크 미연결로 실패통지가 온다:** 시간트리거(16:30)라 드물지만, 절전복귀 직후면
  가능하다. 재시도(기본 3회·30초)가 다 실패하면 실패통지가 온다 — 인덱스는 안전(멱등)하니 다음 주기에 반영된다.

## 운영 메모

- **주기적 재이전:** 개발 PC가 인덱스를 재빌드하면 미니PC 사본이 낡는다 → 4단계를 다시 수행.
- **갱신:** 코드 변경은 개발 기계에서 커밋·푸시 후, 미니PC에서 `git pull`만. 미니PC에서 편집 금지.
- **로그:** 스케줄러 실행 결과는 텔레그램으로, 상세는 태스크 히스토리(`Get-ScheduledTaskInfo`)로 확인.
