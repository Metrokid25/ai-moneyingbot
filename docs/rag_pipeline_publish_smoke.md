# RAG Pipeline Publish Smoke

The RAG pipeline supports pass-gated publish options: `-CommitOnPass`, `-PushOnPass`, and `-CommitMessage`.
The default pipeline run does not commit or push.
The publish gate runs only when `REVIEW_RESULT=PASS` and publish options request it.
`agent_tasks/pending/001-real-daily-archive-wiring.md` is Archive-owned and must not be implemented by the RAG Bot.
