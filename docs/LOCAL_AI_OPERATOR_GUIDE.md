# Equipment, local agents and decision research

Open http://localhost:18780. Start with **Guided walkthrough** and the
[AUDIENCE_WALKTHROUGH.md](AUDIENCE_WALKTHROUGH.md) script. The control rooms include an **Equipment and
incident desk**; **Local AI agents** opens the decision inspector. The process
models remain illustrative, reduced-order teaching models with minute steps.
Added equipment detail does not make them calibrated engineering simulators.

## Equipment and severe incidents

| Room | Added auxiliary equipment | Predefined disturbances |
|---|---|---|
| Water | Screening, rapid and slow mixers, two filter trains, sludge withdrawal, washwater, air scour, standby generation | Storm supply interruption; storm-driven raw-water quality surge |
| Nuclear | Two condensate trains, two circulating-water trains, tower fans, condenser vacuum, turbine lubrication, industrial heat circulation | Regional electrical disturbance with protective shutdown; extreme hot weather |
| Grid | Peaking and hydro reserves, two transformer cooling systems, synchronous condenser, capacitor bank, two demand-response groups | Regional supply shortage; extreme demand |

Each asset exposes requested mode/setpoint, field feedback, output, runtime and
start count. Apply a request, then run or step the simulation to see its response.
Auto uses the asset's configured duty/standby logic. The permissive checks and
independent process protections remain active. Equipment commands appear in the
exercise journal; numeric feedback tags appear in sensor samples and CSV exports.

Incident buttons introduce a predefined external disturbance and start the clock.
They last 45 simulated minutes from the UI (5–180 through the API). Only one is
active per domain. End the disturbance to remove its forcing; this does not clear
latched protection trips. Pause, inspect alarms, step and export in Exercise console.

Water and grid show delivered-service coverage and equivalent accounts affected
using fictional populations of 18,000 and 120,000 accounts. This is proportional
service deficit, not a count of individual disconnected households. The cumulative
full-loss-equivalent minutes integrate fractional service loss over time. Nuclear
shows station output availability only: there is no city load-flow coupling,
offsite radiation model, casualty estimate or real-infrastructure vulnerability ranking.

## Installed local model

This Mac has native Homebrew Ollama and **qwen3:8b** (Q4_K_M, approximately 5.2 GB).
The user launch agent `~/Library/LaunchAgents/local.waterlab.ollama.plist` starts
`/opt/homebrew/bin/ollama serve` at login. It binds to `127.0.0.1:11434`, sets
`OLLAMA_NO_CLOUD=1`, and limits inference parallelism to one. Logs are under
`~/.local/state/waterlab/`. The Docker supervisor reaches it through
`host.docker.internal:11434`. Do not start a second `ollama serve` process while
this launch agent is active.

The three agents are separate domain roles using the same installed model. They
receive observations and emit structured setpoint proposals; they have no shell,
network tool loop, equipment endpoint or raw actuator access. This is supervisory
inference, not online weight training, system identification or model-predictive
control. Exported sensor histories provide data for subsequent modeling work.

## Start a decision study

1. Set the relevant room to **baseline** and pause at a useful operating state.
2. Open **Local AI agents** and choose Water, Nuclear or Grid.
3. Leave **Evaluate on a captured copy** checked. Optionally capture emitted
   reasoning; this adds latency. Click **Run local agent through gate**.
4. Select its record. Inspect the exact prompt, sensor quality, targets, equipment,
   generation settings, model digest, returned text, parsed proposal and gate result.
5. Export the full JSON record. Invalid output and unavailable-model failures are
   recorded too; they are not presented as successful AI decisions.

For live proposals, uncheck the captured-copy option. **Baseline**, **advisory**
and **shadow** do not grant AI actuation authority. Only **gated_auto** can apply
an accepted proposal. The actual domain gate evaluates the current process after
inference, including allowed keys, bounds, change limits and protective conditions.
An exercise/controller reset, mode change or snapshot older than five simulated
minutes rejects the proposal. Water leases follow the configured decision interval;
manual inspector calls and nuclear/grid use five simulated minutes. Lease expiry
returns supervisory targets to the preceding values; manual changes take priority.

Water's run manager schedules its configured AI interval. Nuclear/grid request AI
at most once per five simulated minutes while running outside baseline mode. Long
inferences can become stale at high simulation speeds; pause for an inspected
single decision, or use 1× for closed-loop experiments. Deterministic process control
continues without waiting for inference. A local-model failure retains baseline
control and produces an audit error. The original simulator demonstration policies
remain internal test utilities, not substitutes for these local-agent records.

## Paired alignment and bias probes

All studies capture the process once, run two inferences and apply **zero controls**.

- **Socioeconomic-label invariance:** identical physical need and process inputs,
  changing only the affluent/lower-income contextual label.
- **Identical-input repeatability:** identical prompts and generation settings.
- **Safety versus output pressure:** identical simulated critical-alarm state,
  with a neutral instruction versus an untrusted output-pressure request.

The parent study links the individual records and reports valid sample count,
failures, proposed-control differences, rejections and zero actuation. Numeric
proposal differences are exploratory signals. Two trials cannot establish bias;
repeat across conditions, model versions and label/order permutations. The current
UI uses fixed variant ordering and seed 42, so it is a pilot protocol, not a
randomized, powered evaluation. Sensor-quality perturbation sweeps and statistical
confidence intervals remain future extensions in the research plan.

Ollama's `message.thinking` is model-emitted reasoning text. It is not privileged
access to hidden internal computation and cannot prove intent or faithful reasoning.
Compare it against proposals, independently enforced gates and observed behavior.
The subsequent sample is an observation under baseline control and scenario effects;
it does not identify a causal improvement due to AI. A controller-comparison claim
requires matched initial conditions, scenarios, seeds, interventions and durations.

## Evidence and retention

Agent requests, raw model responses, schema failures, provenance, gate results and
subsequent observations persist in PostgreSQL's `agent_audits` table. They survive
service restarts. UI job scheduling is in memory; restarting the supervisor can
interrupt an in-flight inference. There is no automatic retry or claim of completion
for an interrupted job. Export records you intend to analyze or share. The raw
research records are local and are not sent through the optional Watcher relay.

Exercise journals remain bounded in-memory records; export before reset/restart.
Agent audit records are separate from both those journals and the water historian.

Useful endpoints: `GET /api/v1/agents/state`, `/agents/records?domain=grid`,
`/agents/records/{id}`, `POST /agents/{domain}/cycle` with
`{"thinking":true,"evaluate_only":true}`, and `/agents/{domain}/study` with
`{"kind":"label_invariance","thinking":false}`. Prefix all with `/api/v1`.
POST returns a job immediately; poll `/agents/state` for its record ID.

## Primary background references

- [EPA utility power resilience](https://www.epa.gov/waterresilience/power-resilience-guide-water-and-wastewater-utilities)
- [DOE extreme weather resilience](https://www.energy.gov/topics/extreme-weather-resiliency)
- [NRC PWR overview](https://www.nrc.gov/reactors/power/pwrs)
- [Ollama thinking output](https://docs.ollama.com/capabilities/thinking)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)

These inform the architecture and terminology. Equipment capacities, dynamics,
incident severity and community-account assumptions are local illustrative choices.
