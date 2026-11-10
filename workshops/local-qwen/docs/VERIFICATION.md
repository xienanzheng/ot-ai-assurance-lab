# Verification ledger

This file separates software behavior, integration transport and model quality. Local trial files are retained in ignored `artifacts/`; nothing is uploaded.

## Automated verification

Latest full run: **61 tests passed**, one upstream Starlette/AnyIO deprecation warning. The suite covers contracts, invalid/missing/stale/future/incorrect-unit data, bounded changes, leases, trips, generation fencing, journal failure, idempotent receipts, lost acknowledgements, feedback limits, audit modes, context isolation, cooling reuse, authenticated receiver, read-only profiles and an actual loopback OPC UA server/client. Critical measurements are independently blocked even when the alarm flag is clear.

Six material defects from the independent code review were reproduced and corrected: stale freshness after scan failure, unresolved submissions permitting new work, stop-versus-arm race, overlapping outcome attribution, journal failure leaving ownership stuck, and expired lease persistence on rearm. Additional regressions cover acknowledgement identity and model context from previous exercises.

## Real software and model trials

| Category | Current evidence |
|---|---|
| Local frontend | Production build, 1440px desktop and 390px mobile browser inspection completed; no horizontal overflow; screenshots retained |
| Docker/PostgreSQL/OPC UA water run | Passed nine checks in 120.1 s. Target 1.2→1.0 mg/L; sustained objective at about 114 process seconds. Active feedback stopped on restart; target/receipt retained, new generation, disarmed. `water-runtime-1792906071.json` |
| Local Qwen trial 1 | Valid hold, unsupported claim of protection; 17.8 s cold including 10.1 s load. Failed semantic trial retained |
| Local Qwen trial 2 | Valid hold, incorrect range/wait reasoning; 16.5 s. Failed semantic trial retained |
| Context change after trials | Current protection flags, generation-filtered history, explicit computed above/inside/below and active-wait facts; no weight training |
| Revised Qwen | Valid but unjustified hold, 7.3 s warm. Explicit facts did not resolve its incorrect range/wait reasoning. Not qualified |
| Qwen + Gemma required review | Qwen held in 6.2 s; Gemma returned a matching-hash flag. No command submitted. Gemma's reason was vague and did not establish a correct diagnosis |
| Live cooling portability | Repeat passed, 144.5 s total. Target 12→11°C; sustained objective at about 140 process seconds. Target/receipt persisted across restart, new generation, disarmed control. `cooling-runtime-1792905883.json` |
| Real-time 60-minute endurance | Passed all eight checks over 3,600.04 real seconds, 12 fixture decisions and zero transport/capture errors. `artifacts/endurance-1792906274.json`. This is integration evidence, not model-quality evidence |
| Physical hardware / external SCADA | Not tested |

Reproduce: `scripts/smoke.py`, `scripts/qualify.py`, and `.venv/bin/pytest -q`. Smoke scripts reset the current V2 exercise; do not run them during endurance or another person's local demonstration.

`scripts/verify_runtime.py` adds real-time response plus controller/app restart checks, using the explicitly labelled fixture policy. Environment/model digest evidence is saved separately in `artifacts/environment.json`. New audit records retain requests, successful raw responses, latency and the server-bound snapshot/proposal hash. Errors remain unavailable with a recorded cause. Historical records are not retroactively filled.

The first cooling run reached the objective but failed restart because the app attempted recovery before the receiver listened. That failed artifact remains alongside the passing rerun; the bounded startup retry was added between them.

Browser reconnection was separately tested with Playwright's offline/online switch: the connection-error banner appeared offline and cleared automatically after fresh successful polling. Operator action errors retain their separate state. The browser was restored online after the test.

## Model interface review

See [MODEL_REVIEW](MODEL_REVIEW.md) for 85 local diagnostic calls: focused 4B improved from 4/16 to 8/16 correct development decisions; an 8B comparison reached 11/16 but still missed latched protection. Neither is qualified. Gemma verdicts improved from 8/16 to 12/16, while substantive rationale errors remain. Audit stays optional; the deterministic gate is unchanged.

Latest live model/export check passed six integration assertions with application disabled. Qwen still held without justification and Gemma falsely passed it. This is a failed decision/audit trial, not recovery evidence. Records preserve both responses. Local control was left disarmed, feedback stopped, audit policy off.
