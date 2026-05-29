# RAG ingest boundary implementation

## Goal

Archive export JSONL을 RAG가 import할 수 있도록 첫 ingest 스크립트와 테스트를 만든다.

## Completion Criteria

- scripts/ingest_archive_export.py 추가
- JSONL 한 줄당 article record 로드
- JSONL 필수 필드 검증:
  article_id, title, body_text, url, author, created_at, collected_at, source, content_hash
- 중복 article_id 또는 content_hash skip
- source URL 보존
- chunking 파이프라인으로 넘길 준비 구조 생성
- fixture 기반 테스트 추가: valid input, missing required fields, duplicate article_id/content_hash skip behavior, dry-run behavior
- archive.db 수정 없음
- data 원본 수정 없음
- pytest 통과

## Forbidden

- archive.db write 금지
- src/db.py 수정 금지
- archive 수집 코드 수정 금지
- 실제 네이버카페 접속 금지
