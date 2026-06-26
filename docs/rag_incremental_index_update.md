# RAG Incremental Index Update

크롤러가 새 글을 쌓은 뒤, **전체 재임베딩 없이 신규 글만 색인에 추가**하는 절차다.

스크립트: `scripts/update_rag_index_incremental.py`

## 동작 원리

1. archive.db를 **읽기 전용**으로 읽어 export → ingest(중복 제거) → chunk를 **메모리에서** 만든다 (기존 모듈 재사용).
2. 매니페스트(`data/rag_index_manifest.jsonl`)의 이미 색인된 chunk_id와 비교해 **신규 chunk만** 추린다. 매니페스트가 없으면 마지막 전량 빌드의 `data/embeddings_phase2_ids.npy`로 1회 시드한다.
3. 신규 chunk만 Voyage로 임베딩한다 (재임베딩 비용은 신규분만 발생).
4. Qdrant에 **`--recreate` 없이 upsert**한다. point id가 `uuid5(chunk_id)`로 결정적이라 기존 점은 유지되고 신규만 추가된다(재실행 멱등).
5. 매니페스트에 신규 chunk_id를 append한다.

크롤러 동작/휴식 여부와 무관하게 언제든 실행 가능하다(읽기 전용). 휴식 중이면 동시 쓰기가 없어 더 깔끔하다.

## 사용법

```powershell
# 신규 chunk 수만 확인 (임베딩/적재 없음, 무료)
.\.venv\Scripts\python.exe scripts\update_rag_index_incremental.py `
  --db-path "C:\projects\naver_cafe_archive\data\archive.db" --dry-run

# 신규만 임베딩 후 qdrant upsert + 매니페스트 갱신
.\.venv\Scripts\python.exe scripts\update_rag_index_incremental.py `
  --db-path "C:\projects\naver_cafe_archive\data\archive.db" --execute
```

옵션: `--manifest-path`, `--seed-ids-path`, `--qdrant-path`, `--collection`, `--embed-model`, `--embed-batch-size`, `--upsert-batch-size`, `--limit`.

`--dry-run`과 `--execute` 중 하나는 반드시 줘야 한다(아무것도 안 주면 거부). 신규가 0건이면 `--execute`라도 임베딩/적재 없이 즉시 종료한다.

## Boundary

- archive.db는 읽기 전용으로만 소비한다(원본 변형 금지). 파생물(`data/`, manifest)은 gitignore.
- Trading Bot 파일/`data/` 커밋/실주문과 무관하다.

## Related

- 인덱스 최초 빌드·서빙: `docs/rag_ingest_boundary.md`
- 운영 절차: `docs/rag_agent_operator_runbook.md`
