# 작업명: 실제 daily archive 수집 연결

## 목표

- `scripts/daily_archive.py`의 실제 실행 모드에 기존 `index_tail.py` / `collector.py` / `db.py` 흐름을 연결한다.
- `--dry-run`은 유지한다.
- 실제 수집은 안전장치 없이 무제한 실행되면 안 된다.
- 실제 네이버카페 접속은 명시적인 실행 플래그가 있을 때만 허용한다.

## 범위

- Archive 영역만 수정한다.
- 주요 후보 파일:
  - `scripts/daily_archive.py`
  - `scripts/index_tail.py`
  - `src/collector.py`
  - `src/db.py`
- RAG 파일은 수정하지 않는다.

## 완료 조건

- `pytest` 통과
- `python scripts/daily_archive.py --dry-run` 통과
- 실제 실행 모드는 `--execute` 또는 명시적 플래그 없이는 실행되지 않음
- `data/` 원본을 임의로 삭제하거나 마이그레이션하지 않음
- `archive.db` 파괴적 변경 없음
- `.env` 변경 없음

## 안전 규칙

- 무제한 페이지 순회 금지
- 요청 간 delay 또는 batch limit 없는 실제 수집 금지
- 실패 글은 failed queue 또는 기존 retry state에 기록
- daily report는 사람이 1분 안에 확인할 수 있게 유지
