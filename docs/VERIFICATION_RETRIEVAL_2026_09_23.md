# Retrieval verification — 23 September 2026

Implemented locally; not deployed to the public Cloudflare simulator in this change. Retrieval defaults off and is selectable per decision in the Agent inspection lab.

## Automated checks

- 81 targeted Python checks passed (retrieval, lesson review, agent integration, water timeline and control gate).
- Seven hosted policy checks and seven frontend evidence/status checks passed.
- Frontend production build and whitespace checks passed.
- Existing warnings concern Starlette deprecation and pre-existing infrastructure serialization; no test failure remains.

## Actual local inference

Model: `qwen3:4b`; embedding model: `embeddinggemma`.

Six frozen-state decisions compared retrieval off against requested hybrid across water, grid and conceptual nuclear. Physical/model inputs matched after excluding retrieved knowledge. All three initial hybrid attempts timed out at the original eight-second embedding limit and explicitly used keyword fallback. They are **not semantic-retrieval results**. Water gates rejected both proposals; grid/nuclear returned shadow evaluations with no actuation.

Cold water document embedding preparation subsequently succeeded in 39.806 seconds. The repeated lookup took 64.4 ms with four cached document vectors. This is retrieval-only latency, not end-to-end decision latency. Preparation now allows 60 seconds; decision retrieval allows 30 seconds by default. The final preparation command completed successfully for all three domains without fallback (water 238 ms, grid 431 ms, nuclear 112 ms with the embedding runtime warm).

A separate 21-minute synthetic water timeline used seed 101, the gradual-turbidity scenario, decisions at minutes 10 and 20, and identical initial plant/controller conditions. It executed four additional actual Qwen calls, with recent samples and previous decision/gate information. Both hybrid calls used semantic retrieval successfully without fallback.

| Context | Decisions | Mean full decision seconds | Applied changes | Unsafe samples | Recovery |
|---|---:|---:|---:|---:|---|
| hybrid | 2 | 47.75 | 0 | 0 | Not observed |
| off | 2 | 42.80 | 0 | 0 | Not observed |

All four timeline proposals were rejected by the gate. Neither branch encountered an operating-limit violation within this short horizon. Consequently, this test validates the retrieval/inference/gate/audit path but does **not** establish recovery improvement or decision accuracy. Full decisions were slower with retrieval in this small sample. Warm-up/order effects, one seed, one scenario and short duration preclude broader conclusions. Escalation accuracy and unnecessary interventions remain unmeasured without independently labelled cases.

Raw requests, responses, retrieval provenance and subsequent observations are retained locally under `artifacts/retrieval-2026-09-23/` (ignored by Git), with separate JSON reports and SQLite audit databases. These reports hydrate decision records from the final audit database so later observations are included. No weights were fine-tuned and no real equipment or active hosted session was controlled.

See [setup and repeatable comparisons](PLANT_KNOWLEDGE.md). Run longer timelines and multiple held-out scenarios before deciding whether to enable retrieval by default.
