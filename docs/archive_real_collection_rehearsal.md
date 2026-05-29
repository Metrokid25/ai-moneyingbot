# Archive Real Collection Rehearsal Checklist

Use this checklist before any real Naver Cafe archive collection. Do not run
real collection during rehearsal. The first real run must happen only after an
explicit operator approval.

## 1. Repository State

- Confirm the active branch and remote sync state:
  - `git status -sb`
  - Expected: the working branch is synchronized with its upstream.
- Confirm only expected untracked helper files remain:
  - `scripts/_step3_verify_v2.py` may be untracked.
  - Do not edit, stage, commit, or delete `scripts/_step3_verify_v2.py`.
- Confirm there are no tracked changes before rehearsal:
  - `git diff --stat`
- Do not use `git add .`.

## 2. Safety Boundaries

- Do not modify `.env`.
- Do not delete, reset, migrate, or initialize `archive.db`.
- Do not delete or rewrite `data/`.
- Do not modify RAG files or vector index artifacts.
- Do not run a real collection command during rehearsal.
- Do not run any `daily_archive.py --execute` command unless the operator has
  explicitly approved the real collection run.

## 3. Required Rehearsal Commands

Run these commands before asking for real collection approval:

```powershell
pytest --basetemp=.tmp\pytest
python scripts/daily_archive.py --dry-run
python scripts/daily_archive.py
git status -sb
git diff --stat
```

Expected results:

- `pytest` passes.
- `--dry-run` uses mock data only and reports no browser, network, or archive DB
  writes.
- Default `python scripts/daily_archive.py` prints safety guidance only.
- `git diff --stat` is empty unless a deliberate reviewed change is in progress.

## 4. Data and DB Readiness

Before a real run, record the current archive state:

- Confirm `data/archive.db` exists if the run is expected to write to the
  production archive DB.
- Record current DB counts using read-only inspection when needed.
- Confirm whether a backup is required by the operator before the first real
  run of the day.
- Never delete or reinitialize `archive.db` as part of rehearsal.
- Never delete source files under `data/`.

## 5. Real Collection Approval Gate

Real collection is allowed only after explicit operator approval. The approved
command must include both:

- `--execute`
- `--limit N`
- `--list-url <URL>`

The first real run should use a very small bounded limit, for example:

```powershell
python scripts/daily_archive.py --execute --limit 2 --list-url "<URL>"
```

Do not run the example command during rehearsal.

## 6. Post-Run Checks

After an approved real run, inspect:

- CLI summary:
  - `saved`
  - `duplicates`
  - `failed`
- Daily report under `reports/daily/`.
- Operational state under `state/`.
- `failed_queue.json` for failed list, row, or body collection items.
- DB counts and any newly indexed article IDs, using read-only queries unless a
  specific follow-up fix is approved.

## 6.1 Optional 24-Hour Loop

After a successful first bounded run, an operator may approve the loop wrapper:

```powershell
python scripts/run_daily_archive_loop.py --list-url "<URL>"
```

Defaults:

- `--duration-hours 24`
- `--interval-seconds 600`
- `--limit 10`

The loop runs one `daily_archive.py --execute --limit N --list-url <URL>` pass
at a time, waits for the pass to finish, then sleeps for the interval. It stops
on non-zero return codes, block/login/captcha/permission signals, or failed
count above the configured threshold.

## 7. Stop Conditions

Stop immediately and inspect before retrying if any of these occur:

- Login, captcha, permission, or age-verification block signal.
- Unexpected network/browser error.
- `failed` count is non-zero and the reason is unclear.
- `failed_queue.json` contains repeated failures for the same target.
- The report indicates no rows were discovered when rows were expected.
- Any tracked changes appear in forbidden areas such as `.env`, `data/`, RAG
  files, or `scripts/_step3_verify_v2.py`.

## 8. Reporting

When reporting rehearsal or real-run readiness, include:

- Branch and `git status -sb`.
- Test result.
- Dry-run result.
- Default execution safety guidance result.
- Whether real collection was run.
- If real collection was approved and run, include the exact bounded command and
  the resulting `saved`, `duplicates`, `failed`, report path, and failed queue
  status.
