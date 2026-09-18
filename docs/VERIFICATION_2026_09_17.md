# Release verification — 17 September 2026

## Results

| Check | Observed result |
|---|---|
| Python suite, network-disabled test container | 139 passed; 6 skipped; 16 dependency/serialization warnings |
| Hosting policy and static-response tests | 10 passed |
| Frontend evidence/status tests | 7 passed |
| Clean source-tree npm installation and production build | Passed |
| Hosted frontend build | Passed |
| Cloudflare deployment dry run | Worker compiled and Linux AMD64 container built |
| Public recorded site | HTTPS, real HTML, dataset loading and five demo chapters verified |
| Public mobile view | No horizontal overflow at 390 px |
| Hosted browser, local Cloudflare runtime | Session entry, simulator render and session exit passed; no JavaScript exceptions |
| Local supervisor upgrade | Healthy; 13 eligible existing audits archived; zero lessons approved |

The skipped Python tests are three Compose integration tests and three optional mechanistic-interpretability tests. They were not enabled in that network-disabled unit-suite invocation. Separate hosted integration checks below exercised actual services; no new activation study was run.

## Hosted integration with real model API

`scripts/check_hosted_sessions.mjs` ran against the local Cloudflare Worker runtime, using actual containerized simulation services and real Cloudflare Workers AI requests to `@cf/qwen/qwen3-30b-a3b-fp8`.

- Two server-issued visitor sessions received independent containers and histories.
- Unauthenticated API calls and cross-origin session creation were denied.
- Water: ten-minute stepping, 82 sensor outputs, fault injection, pause and JSON export worked; the second visitor's state and run list were unchanged.
- Nuclear and grid: disturbances, stepping and sensor reads worked; the second visitor's clocks remained unchanged.
- Each domain produced a model response and a persisted audit with cloud provenance. The gates rejected all three tested proposals; no controls were applied.
- Batch studies were denied in the public route. Ending a session denied further access.

A separate grid test enabled gated automatic control under nominal conditions and called the real model. It proposed unsupported bus-voltage control keys. The deterministic gate rejected the proposal, `applied` remained false, and the recorded controls remained unchanged after six more simulated minutes. This demonstrates rejection and continuity of rule-based control, **not successful optimization**. A plausible rationale and high self-reported confidence did not make the proposal valid.

The session policy unit tests cover concurrency/daily admission caps, expiry, per-session and global AI allowances, request pacing, request-size bounds, preservation of forwarded POST bodies and removal of client-supplied container-port headers.

## Defects found and corrected

- Static Worker response construction initially serialized a Response object as text. Regression coverage now checks HTML bytes, content type and missing-file status.
- Scientific Python/OPC UA cold startup exceeded the container SDK's default startup allowance. Explicit 90-second readiness limits resolved the test startup failure.
- Premature request cloning locked POST bodies. The forwarding helper now reads bounded bodies before constructing the internal request.
- The static asset configuration needed explicit root-to-index handling in the hosted Worker.
- The recorded public site's navigation now links to the repository instead of the visitor's localhost.

## Remaining acceptance step

Workers Paid was not enabled, so **the full hosted simulator has not been deployed or tested in Cloudflare production**. Only the recorded dashboard is public. After enabling the plan, deploy `deploy/cloudflare-live`, repeat the session test against the public hostname, and verify production container cleanup, websocket behavior and billing. The local end-to-end result does not substitute for that production acceptance test.

No test establishes engineering fidelity for real equipment, verified air-gapping, faithful access to internal reasoning, improved recovery, or absence of model bias.
