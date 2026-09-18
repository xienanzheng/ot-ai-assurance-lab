# Hosted production verification — 18 September 2026

The full simulator is deployed at https://ot-aigent-simulation.night-zone.com. The recorded dashboard remains at `/research.html`.

- Worker version: `027a182f-8c4d-406b-a617-cb13ea65fdc0`.
- Container image: `sha256:cc52d330d7fe90fdd94b36d741dee053e9092a5259a96f3b21fc7ffbe6b7655c`.
- Inference: Cloudflare Workers AI, `@cf/qwen/qwen3-30b-a3b-fp8`.

## Public integration test

Executed against the public HTTPS hostname, using real deployed containers and real API inference:

```sh
node scripts/check_hosted_sessions.mjs https://ot-aigent-simulation.night-zone.com --ai
```

| Check | Observed result |
|---|---|
| Session boundaries | Separate server-issued sessions; unauthenticated calls and cross-origin creation denied |
| Water | Ten-minute stepping, sensor reads, fault injection, pause and JSON export passed |
| Nuclear and grid | Disturbance scenarios, stepping and sensor reads passed |
| Visitor isolation | The second visitor's clocks and run history remained unchanged |
| AI in all three domains | Real model responses reached their gates and persisted with cloud provenance |
| Gates in disturbed scenarios | All three tested proposals rejected; no actuation |
| Batch studies | Public route denied as intended |
| Session termination | Further API access denied |

## Browser walkthrough

A fresh desktop browser completed session start, Water overview, Water HMI, Nuclear PWR, Power grid, Exercise console and AI decisions. It received 12 live WebSocket sensor frames, with 82 water sensor outputs per frame. No JavaScript page errors or failed API responses were observed in this final walkthrough.

The browser ran a separate nominal-water evaluation, opened its decision evidence and downloaded the full JSON record. The gate accepted that proposal; evaluation-only mode retained `applied=false`. The record explicitly identifies cloud inference. This is evidence that proposals can pass the gate, not proof of beneficial control or process recovery.

The 390-pixel mobile layout had no horizontal page overflow. Ending the browser session returned to the start screen.

## Defect found and corrected

The initial production AI check failed twice: the model returned valid JSON with an explanation longer than the water proposal's 280-character limit. Local validation rejected it and retained baseline control. The adapter had requested generic JSON while placing the schema only in prompt text.

The adapter now sends the existing proposal schema through the provider's `json_schema` response format. A replay of the failing input produced a valid-length explanation, then the complete public integration and browser tests passed. The deterministic gate and local schema validation remain unchanged. Malformed future outputs still fail closed; structured-output mode is not a guarantee of model correctness.

A regression test first failed against generic JSON mode, then passed with schema forwarding. All 11 hosting/static policy tests and all seven frontend status/evidence tests passed. The hosted production build also passed. The preceding release's Python results are documented separately; this change does not modify the Python simulation engines.

## Scope and limits

The tests use temporary synthetic sessions, including non-actuating model evaluations. They do not establish reliable AI optimization, real-equipment fidelity, verified air-gapping, internal-reasoning access, or absence of model bias. The hosted sandbox uses cloud inference; the local offline deployment remains a separate setup.

Existing limits remain three concurrent sessions, 20 minutes per session, ten AI calls per session, 20 session admissions per UTC day and 200 AI calls per UTC day. These bound application usage, not total dollar billing. Actual container and inference charges should be assessed from measured Cloudflare usage.
