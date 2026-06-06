# 055 RAG Research Retrieval Qdrant Availability Check

Status: done

## Scope

- Add a Qdrant backend availability check to the research retrieval runner.
- Distinguish live no-result searches from unavailable or empty retrieval backends.
- Preserve DB-only behavior and reuse the existing RAG retrieval defaults.

## Findings

- `search_qdrant_phase2.py` and `run_rag_research_retrieval.py` both use `rag_retrieval.DEFAULT_QDRANT_PATH` and `rag_retrieval.DEFAULT_COLLECTION`.
- Default Qdrant path: `data/qdrant`.
- Default collection: `goodmorning_chunks`.
- `evaluate_rag_retrieval_set.py` is mock/dry-run only and does not open Qdrant.
- `run_rag_focused_tests.py` verifies runner help and tests; it does not execute live retrieval.
- Current local `data/qdrant/meta.json` has no `goodmorning_chunks` collection, so live retrieval is unavailable in this workspace.

## Validation

- `pytest tests/test_rag_research_retrieval.py --basetemp=.tmp/rag_research_retrieval_pytest`
- `python scripts/run_rag_focused_tests.py`
- `python scripts/run_rag_research_retrieval.py --questions-file agent_reports/rag-research-questions-20260601-154441.jsonl --top-k 5`
- `git diff --check`
