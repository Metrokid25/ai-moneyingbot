# RAG Agent Mission

The RAG agent owns small, verifiable improvements to retrieval, chunking,
answer context, answer grounding, RAG tests, RAG reports, RAG documentation,
and the RAG web UI.

## Allowed Scope

- RAG eval strengthening.
- Retrieval regression strengthening.
- Answer grounding improvements.
- Source metadata quality improvements.
- RAG web UI improvements.
- Pipeline and report summary improvements.
- Fixture expansion.
- Focused test strengthening.
- Documentation for RAG workflows.

## Forbidden Scope

- Archive collection, crawling, browser automation, parser behavior, or archive
  writes.
- Naver Cafe access.
- Changes to `.env`, `archive.db`, raw `data/` originals, or
  `scripts/_step3_verify_v2.py`.
- Changes to `scripts/daily_archive.py`, `scripts/index_tail.py`,
  `scripts/batch_recollect.py`, `src/browser.py`, `src/parser.py`,
  `src/collector.py`, or `src/indexer.py`.

## Planner Rules

- Generate a next RAG task only when no actionable RAG task is pending.
- Generate exactly one task per planner run.
- Keep generated tasks small enough for one later autorunner pass.
- Write generated tasks under `agent_tasks/pending/`.
- Do not implement the generated task in the same planner run.
