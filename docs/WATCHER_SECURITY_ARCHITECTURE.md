# Watcher security architecture

## Purpose

Apollo Watcher can add behavioural monitoring and forensic review to the lab. It must not become a controller, safety system, or dependency for deterministic plant protection.

The architecture uses four established patterns:

- Defence in depth
- A reference monitor around AI activity
- Out-of-band security monitoring
- Least privilege with explicit trust zones

Watcher starts in observe-only mode. Its findings appear in a security console and audit record. They do not enter the control loop.

The standard Watcher coding-agent client is intentionally not installed for this integration. WaterLab uses a dedicated runtime relay so Codex and Claude transcripts are outside the data path.

## Implemented observer path

The current implementation includes:

- An allowlist exporter in `supervisor-api`
- A named Docker outbox volume
- A `watcher-relay` service behind the optional `watcher-observer` Compose profile
- A separate `monitor_net`
- A read-only outbox mount inside the relay
- No Watcher result path back to the supervisor or PLC controller
- Dry-run mode as the default

Only proposals whose source begins with `ollama` enter the outbox. Manual actions, test proposals, deterministic fallbacks, prompts, sensor dumps, memory contents, source files, and chat transcripts are excluded.

## Trust zones

```text
ZONE 1: OT SIMULATION                  ZONE 2: CONTROL APPLICATION

plant-sim <---- OPC UA ---- plc-control <---- approved setpoints ---- supervisor-api
    |                                ^                                  |
    |                                |                                  |
    +------ deterministic state -----+                       append-only decision event
                                                                      |
                                                                      v
                                                          decision_events database

--------------------------------------------------------------------------
                         ONE-WAY OBSERVATION BOUNDARY
--------------------------------------------------------------------------

ZONE 3: MONITOR RELAY                   ZONE 4: WATCHER

read-only event cursor ----> sanitizer ----> Watcher ingest and grading
                                  |                    |
                                  |                    v
                                  +------------> monitoring database
                                                       |
                                                       v
                                               human security console
```

## Network segregation

### `ot_net`

Contains only:

- `plant-sim`
- `plc-control`
- The OT-facing side of `supervisor-api`

Watcher is never attached to this network. OPC UA remains unpublished. Watcher has no route to the plant simulator or PLC controller.

### `app_net`

Contains:

- `supervisor-api`
- Application database
- Web dashboard

The supervisor writes decision records here. It does not call Watcher and does not wait for a Watcher response.

### `monitor_net`

Contains:

- `watcher-relay`
- A self-hosted Watcher deployment, if used
- A separate monitoring datastore, if required

The relay is the only dual-homed monitoring component. It makes outbound requests but exposes no listening control endpoint. Its application-database credential is read-only and restricted to an append-only decision-event view.

For Apollo's hosted service, the relay receives outbound HTTPS access only to the documented Watcher hostname. No inbound route is opened.

## Starting the observer safely

First run locally in dry-run mode:

```sh
WATCHER_ENABLED=true WATCHER_DRY_RUN=true docker compose --profile watcher-observer up -d --build watcher-relay
```

This reads allowlisted decision events and records dry-run observer entries. It sends nothing to Apollo.

After creating a Watcher organization API key, place it in the local `.env` file and set:

```text
WATCHER_ENABLED=true
WATCHER_DRY_RUN=false
WATCHER_API_KEY=<set locally>
```

Then start the same Compose profile. Do not paste the API key into chat, source code, screenshots, or committed configuration.

## Preventing the controller AI from influencing Watcher

The controller model must not see Watcher prompts, thresholds, grader scores, administrative settings, or raw findings.

Controls:

1. The supervisor stores a canonical structured event. The model cannot select event fields or destination addresses.
2. Free-text model explanations are treated as untrusted data. They are length-limited, escaped, and labelled as model output.
3. The relay never concatenates model text into a monitor system prompt.
4. Numerical proposals, sensor-quality flags, gate decisions, and outcomes use a fixed JSON schema.
5. Watcher administration credentials exist only in the monitoring zone.
6. The relay receives an ingest-only credential. It cannot change graders, policies, users, or retention settings.
7. Monitor findings are not automatically inserted into Ollama memory.
8. A human can promote a reviewed finding into a new deterministic rule through a separate change process.

The AI necessarily influences the event being examined because its proposal is the subject of monitoring. It cannot influence the monitor's policy, configuration, or authority.

## Preventing Watcher from controlling the system

Watcher is observe-only in the first release.

Controls:

1. Watcher has no `ot_net` interface.
2. Watcher has no OPC UA client, actuator certificate, plant token, or supervisor write credential.
3. The relay has no command endpoint and does not accept callbacks.
4. The supervisor never reads Watcher verdicts during its control loop.
5. Watcher cannot modify the decision-event source records.
6. Monitoring failure does not stop deterministic control. It creates a `MONITORING_DEGRADED` application alert.
7. Reactor protection, water interlocks, grid protection, and emergency-stop behaviour remain deterministic.
8. The web console displays Watcher findings from a reporting path that has no control methods.

This means Watcher can detect, report, and support investigation. It cannot start, stop, approve, reject, or modify a simulated actuator command.

## Event schema

Each monitoring event should contain:

```json
{
  "event_id": "uuid",
  "run_id": "uuid",
  "domain": "water | nuclear | grid",
  "simulation_time": "ISO-8601 timestamp",
  "scenario": "scenario identifier",
  "controller_mode": "advisory | shadow | gated_auto",
  "trusted_state": {},
  "untrusted_channels": [],
  "recent_trends": {},
  "retrieved_memory_ids": [],
  "proposal": {},
  "deterministic_gate": {},
  "applied_setpoints": {},
  "result_after_interval": {},
  "model_id": "configured model",
  "policy_version": "version identifier"
}
```

Do not include:

- Hidden reasoning
- Environment variables
- API keys or credentials
- Host filesystem paths
- Real network addresses
- Raw OPC UA endpoint details
- Plant-specific identifiers
- Unbounded database contents

## Runtime responsibility matrix

| Component | Can observe | Can propose | Can approve | Can actuate | Can configure Watcher |
| --- | --- | --- | --- | --- | --- |
| Ollama controller | Sanitized plant snapshot | Bounded setpoints | No | No | No |
| Deterministic gate | Snapshot and proposal | Modified safe values | Yes | No | No |
| PLC controller | Approved setpoint lease | Raw actuator command | No | Yes | No |
| Watcher relay | Append-only event view | No | No | No | No |
| Watcher | Sanitized decision events | Findings only | No | No | Administrative role only |
| Human operator | Dashboard and findings | Manual bounded request | Operational confirmation | No direct write | No |
| Security administrator | Watcher configuration and audit | Policy changes | No plant approval | No | Yes |

## Optional future veto mode

A later release could allow Watcher to request a human hold, but this changes its safety role and availability impact. It should be a separately reviewed feature.

Even in that mode:

- Watcher would return only `clear`, `review`, or `high_risk`.
- Only a local deterministic policy-enforcement service could interpret the verdict.
- A missing, late, or malformed result would return AI control to baseline.
- Watcher would still have no actuator or PLC connection.
- Protection systems would remain independent.

The first release should remain observe-only until false-positive, false-negative, latency, and outage tests are complete.

## Deployment recommendation

### Development monitoring

Use the official Watcher client for interactive Codex or Claude Code development sessions only after approving its transcript collection. The hosted free service sends recorded session content to Apollo's deployment.

### Runtime monitoring

Do not point the Ollama control loop directly at the coding-agent hooks. Build the relay against Watcher's documented HTTP API or Python SDK. Begin with simulated, sanitized simulation records.

### Sensitive environments

Prefer a self-hosted Watcher deployment with a reviewed retention policy, separate administrator identity, restricted network egress, and documented LLM-provider data paths. Self-hosting the Watcher server does not by itself mean grading is local. The configured grading providers may still receive transcript content.

## Fail-safe behaviour

| Failure | Required behaviour |
| --- | --- |
| Watcher unavailable | Continue deterministic baseline, queue sanitized events, show monitoring degraded |
| Relay unavailable | Continue deterministic baseline, retain append-only source events |
| Invalid Watcher result | Ignore result and raise monitoring-quality alert |
| Suspected prompt injection | Quarantine event for human review, do not feed it to model memory |
| Controller model unavailable | Continue deterministic baseline |
| Sensor integrity failure | Block AI proposal through the deterministic gate |
| Database unavailable | Continue local deterministic protection and stop AI application |

## Validation plan

1. Run Watcher in observe-only mode for every existing scenario.
2. Inject unsafe proposals and confirm Watcher can report them but cannot change an actuator.
3. Attempt connections from the Watcher container to OPC UA and verify network denial.
4. Attempt to modify Watcher policy with the relay credential and verify authorization denial.
5. Put prompt-injection text in the model explanation and verify it remains inert data.
6. Disconnect Watcher and confirm baseline control continues.
7. Compare Watcher findings with deterministic gate outcomes.
8. Measure grading latency, missed incidents, and false alarms before considering a human-hold workflow.
