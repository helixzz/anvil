# Crash recovery

Anvil 1.0.0 is **crash-safe by design**: an API restart mid-benchmark
cannot silently lose work or record a broken run as success.

## What happens on restart

The FastAPI lifespan runs `reconcile_on_startup()` before the queue
worker takes its first job. This function:

1. Finds every run with `status IN (preflight, running)` and marks
   them `failed` with:
   > API restarted while this run was in progress; partial state is
   > unrecoverable. Re-queue the run to try again.

2. Finds every run with `status = queued` and re-pushes them into
   the in-memory `asyncio.Queue`. This catches runs that were
   committed to Postgres but never reached `queue.put()` because
   the API process died in between.

3. Logs `anvil_reconciled` with `requeued_count` and
   `requeued_ids` so operators can see what happened.

Reconciliation is idempotent — running it twice produces the same
result. Failures during reconciliation are logged and do not block
startup.

## Runner disconnect handling

Anvil's runner RPC enforces an **explicit terminal-event contract**.
Every successful run ends with exactly one of:

- `run_complete`
- `run_failed`
- `run_aborted`

If the runner's unix-domain socket closes (EOF) or the backend's
read times out (3600 s default) **before** one of those events
arrives, `RunnerClient.run_benchmark()` raises
`RunnerStreamTruncated`. The orchestrator's worker catches the
exception and marks the run `failed` with a clear message.

This is the guard against a truncated fio that would otherwise fall
through to the `smart_after` / `status=complete` path and quietly
publish broken numbers.

## Postgres outage mid-run

If the database becomes unreachable while a run is in progress:

- The in-flight fio keeps running inside the runner container
- Attempts to persist `phase_sample` / `smart_sample` events fail
  with a logged error
- If the error propagates out of `_execute_run`, the worker's
  except-handler calls `_safe_mark_failed()`, which also handles DB
  errors and **does not** re-raise. The worker loop survives.

When the DB comes back, you'll have a `failed` run plus whatever
metrics landed before the outage. Re-queue to re-run.

## Bootstrap admin

On every boot, Anvil ensures at least one active admin exists:

- If any `role=admin, is_active=true` user is in the table → no-op
- Else if a user named `admin` exists (even if disabled or in a
  different role) → promote that row
- Else → create a fresh `admin` row

The password is always the first 16 characters of
`ANVIL_BEARER_TOKEN`. Rotate it immediately after first login.

## Force-repair paths

There's no CLI for manual repair yet; everything goes through the
API. If you need to force a stuck run into `failed`:

```bash
# Manually via psql (Postgres admin only)
UPDATE runs SET status='failed',
  error_message='force-reset by operator',
  finished_at=NOW()
WHERE id = '01K...' AND status IN ('preflight', 'running');
```

After the update, call `POST /api/runs/{id}/abort` to broadcast a
`run_aborted` WebSocket event to any watching UI.
