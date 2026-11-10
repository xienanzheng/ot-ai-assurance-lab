# Local walkthrough and test procedure

Run all commands from this standalone repository. Do not use V1 compose files or its `.env`.

## Timing and ownership

- Real time is **1×**. Acquisition runs about once per second; database samples are saved about every five process seconds.
- These packages use a 60-second response constant, 90-second observation window and 30-second in-band dwell requirement.
- Current required measurements must be no older than five seconds. Captured decision evidence has a separate maximum age of 30 seconds; both captured evidence and fresh live conditions are checked.
- Each accepted target has a five-minute control lease. On expiry authority is disarmed; the simulator holds its last accepted target. This is a bench behavior, not a site-specific fallback design.
- Feedback is capped at 12 decision calls and 60 wall minutes. Its observation window starts from the accepted action. The model cannot shorten it.
- Stop, protection changes, restart or a broken acquisition path disarm authority. A cleared reading does not clear a latched trip. Only **New bench session** explicitly resets the exercise.

## Water test

Choose **New bench session** and **Load exercise**, then fixture, audit off, arm and apply. Initial measured residual is 1.4 mg/L and target 1.2 mg/L. Fixture proposes 1.0 mg/L. The live measurement should gradually approach the accepted target, with the objective band 0.95–1.10 mg/L.

```sh
.venv/bin/python scripts/smoke.py --provider fixture --apply
```

The smoke script resets the current bench, makes one decision and saves a timestamped record. It does not wait for sustained recovery. To assess outcome, allow at least a few minutes, inspect the measured trend and the record's outcome, then export the session.

Choose Qwen to test actual reasoning:

```sh
.venv/bin/python scripts/smoke.py --provider qwen --apply
.venv/bin/python scripts/smoke.py --provider qwen --apply --audit required
```

These are separate exercises: each invocation resets the bench. A structured hold can still be wrong. Read the rationale and current facts, not just parse success or the audit badge.

## Audit modes

| Mode | Behavior |
|---|---|
| off | No audit model call; deterministic gate still runs |
| observe | Audit runs after evaluation/application; a later flag does not undo a target |
| required | Audit must pass before submission; flag, timeout, malformed reply or mismatched evidence blocks application |

The optional audit is another model judgement. It does not replace deterministic checks. Cold Qwen plus cold Gemma may exceed the captured-state age limit; do not loosen limits merely to force acceptance.

## Fault checks

Use the scenario selector to try drift, critical, no flow, bad sensor, stale sensor and override. Each scenario transition stops current feedback. Arm only when protection and required data permit it.

- **Drift:** bounded actions may compensate, but the cumulative limit still applies.
- **Critical:** empty automatic actuation; operator checks remain useful.
- **Normal after critical:** the trip remains latched; this is not permission to recover automatically.
- **Bad/stale/no-flow:** required evidence is invalid; no commands are applied.
- **Override:** operator/forced equipment ownership prevents automatic adjustments.

## Cooling portability test

Stop any run before switching. Both services load the same package; never switch only the app.

```sh
PROCESS_PACKAGE=cooling docker compose up -d --force-recreate controller app
.venv/bin/python scripts/smoke.py --provider fixture --apply
```

The same generic UI and control path now show temperature in °C. Initial measured temperature is 14°C, target 12°C, fixture target 11°C, objective 10.5–11.5°C. No water-specific code edit is needed.

Return to water:

```sh
PROCESS_PACKAGE=water docker compose up -d --force-recreate controller app
```

Records persist across switches and include their package hashes. Model context excludes other packages and earlier control generations.

## Endurance and restart

```sh
.venv/bin/python scripts/qualify.py --minutes 60 --provider fixture
```

Close the browser while this runs; the server owns scheduling. Keep the computer awake and avoid other bench actions. The evidence file is updated under `artifacts/`. A short run is a smoke test, never a substitute for the 60-minute run. The fixture run tests integration stability, not Qwen/Gemma decision accuracy.

For a separate restart test: export a run, stop feedback, restart the two V2 services and confirm target persistence, new generation, disarmed control and retained records:

```sh
docker compose restart controller app
```

Do not inject restarts into a clean endurance run and later report it as uninterrupted.

## Evidence and diagnostics

- UI **Export evidence** / `GET /api/export`: package, exact model inputs/output, gate, command receipt, readback, observations and events.
- `artifacts/`: ignored local trial evidence; no uploads.
- `docker compose logs --tail 100 app controller`: service diagnostics.
- Inference unavailable: verify local Ollama is running and the named model is installed. The application does not silently switch to fixtures or a cloud model.
- Unknown command result: stop, reconcile by restarting the supervisor, inspect the receipt. Do not retry the same intention with a new ID just to bypass uncertainty.
- Records currently have no automatic retention policy. Export and manage storage before a long-running deployment. `down --volumes` destroys the V2 database; use only for an intentional clean bench.
