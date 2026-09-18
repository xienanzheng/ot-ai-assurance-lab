# Critical-event and reviewed-lesson memory

The supervisor preserves critical sensor snapshots and AI audit evidence in `critical_events`. A separate `lesson_versions` table stores candidate lessons and each operator review. Normal run resets do not delete either table. Both use the local historian database; deleting its Docker volume deletes this memory too.

The loop is **observe → archive → propose → review → retrieve → measure**. This is retrieval of reviewed lessons, not reinforcement learning or model-weight training. Improved performance has not been demonstrated.

## Operator workflow

Run these commands from the repository root, with the local Docker stack running:

```sh
docker compose exec supervisor-api python -m app.lesson_memory backfill
docker compose exec supervisor-api python -m app.lesson_memory events
docker compose exec supervisor-api python -m app.lesson_memory event EVENT_ID
docker compose exec supervisor-api python -m app.lesson_memory propose \
  --event EVENT_ID --text 'A concise observation supported by this event.' --days 30
docker compose exec supervisor-api python -m app.lesson_memory list
docker compose exec supervisor-api python -m app.lesson_memory review LESSON_ID \
  --version 1 --status approved --operator YOUR_NAME \
  --reason 'Checked the source evidence and applicability.'
```

Review the saved observation and subsequent outcome before approving. An audit agent may suggest the candidate text; its judgment alone cannot approve it. Use `--status rejected` to reject a candidate or `--status revoked` with the current version to withdraw an approved lesson. Concurrent or stale reviews are rejected.

## Retrieval boundaries

- Only approved, unexpired latest versions enter a prompt, at most three per exchange.
- Domain, scenario and model name must match the source event exactly.
- Every lesson keeps source-event IDs, review reason, operator name and version.
- Lessons are untrusted context. They never change control limits, protection, permissions or the deterministic gate.
- `LESSON_MEMORY_ENABLED=false` disables prompt retrieval. Compose enables it by default, but a new lab has no approved lessons.
- The public hosted sandbox disables shared lesson retrieval and has temporary, per-session storage. Public visitors cannot approve lessons for the local lab.

Water alarm snapshots are collected during active sampled runs. AI gate failures, critical context and measured outcomes are archived from all three domain audit paths. This is not a complete archive of every independent nuclear/grid alarm. Model matching currently uses a name, not an immutable weights digest. Retained audit manifests help investigation, but reviewed lessons should be revoked when a model changes under the same name.

The application appends versions, but this is not a cryptographically immutable journal. A database administrator can alter records. Operator CLI access is the approval boundary; the prototype has no production identity/role system. Back up the database separately and establish retention limits for extended research use.

Evaluate any proposed improvement with fixed scenarios/seeds, repeated trials, memory enabled versus disabled, and adverse cases. Gate acceptance and a plausible rationale do not establish recovery, efficiency, alignment, or faithful access to internal reasoning.
