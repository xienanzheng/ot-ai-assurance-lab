# Module boundaries and extension contract

## Implemented interfaces

| Module | Owned responsibility | Replace/configure through | Must preserve |
|---|---|---|---|
| Process package | Units, limits, objective, response timing, relationships, SOPs and approved check IDs | `process_packages/*.json` and `registry.json` | Validated schema, content hash, reviewed semantics |
| Observation adapter | Read measurements and quality with source timestamps | `OpcSource.capture(package)` | Coherent snapshot, source age, quality, package identity; no fabricated freshness |
| Context builder | Current state, calculated facts, relevant history and package knowledge | `Supervisor.context(snapshot)` | Generation isolation; conditional SOPs distinguished from active alarms |
| Decision provider | Return `Proposal` | `decide(context)` | Structured hold/adjust/escalate, finite target only for adjust; concise evidence |
| Audit provider | Independently review the captured proposal | `audit(context, proposal)` | Exact evidence hash, concise reason, unavailable remains unavailable |
| Gate | Deterministic eligibility | `gate(...)` and receiver revalidation | Quality, protection, timing, range, step and cumulative limits |
| Command transport | Submit identified intent and query its status | `ReceiverClient` | Durable intent, matching command/hash/generation acknowledgement, explicit unknown outcome |
| Controller | Own accepted target, scan and process state | `Controller` | Atomic target/receipt journal, lease, generation fencing, disarmed restart |
| Outcome monitor | Separate target acceptance from measured response | `Supervisor.observe(...)` | Valid samples, dwell time, supersession and interruption attribution |
| Journal and UI | Preserve evidence and show status | PostgreSQL / local API / React | UI never owns the loop or creates arbitrary endpoint/path mappings |

The Python interfaces are deliberately small; there is no runtime marketplace, uploaded Python plugin or arbitrary browser-selected PLC endpoint.

Machine-readable schemas live in `contracts/`; regenerate with `.venv/bin/python scripts/export_contracts.py`. JSON Schema describes field shapes. Cross-field consistency (for example, a target is required only for `adjust`) and live eligibility still require the Python validators and gate; schema validity alone is not authorization.

## What a new package can change today

Water disinfection and cooling both fit the current process family:

`value_next = target + disturbance + (value - target - disturbance) × exp(-dt / response_seconds)`

Flow and protection conditions can inhibit that response. A new instance of this same family can supply another sensor/unit, setpoint bounds, lag, objective and SOPs, then register its filename. The registry rejects traversal and package identity mismatches. Changes alter the package hash and require a controller restart and explicit arming.

This does **not** yet support a multi-stage production line, coupled tank network, discrete recipe sequence or arbitrary multiple-actuator controller. Those need a process adapter and capability contract extension, with a new test suite. A JSON file cannot establish the correct physical relationships by itself.

## Add a process instance

1. Copy a package within `process_packages/`; assign a distinct ID and version.
2. Define sensor IDs, engineering units and checks from a reviewed process description.
3. Set bounds, permissible change per exchange, cumulative excursion, lag, waiting time and sustained-outcome duration.
4. Write explicit relationships and SOP context. These are retrieval/input context, not changes to model weights.
5. Register the filename in `registry.json`; arbitrary external paths are rejected.
6. Add tests for normal, warning, critical, stale/bad measurements, conflicting protections, delayed response and failed acknowledgement.
7. Run the package with `PROCESS_PACKAGE=<id> docker compose up -d --force-recreate controller app`.
8. Qualify its fixtures and real model trials separately before considering any new integration stage.

## Physical-site extensions still required

| Site-specific component | Needed before physical integration |
|---|---|
| Tag binding | Reviewed OPC UA NodeIds or protocol registers, types, scaling, units, quality, source clocks and coherent snapshot grouping |
| Read-only acquisition | External server identity/certificates, least-privilege account, namespace/version checks, disconnect and timestamp tests |
| PLC command mailbox | PLC-programmed capability allowlist, request ID, generation/ownership, expiry, independent limits, acceptance/rejection and acknowledged actual target |
| Local authority | PLC interlocks, operator priority, communications-loss behavior and manual takeover independent of any model |
| Dynamics and sequence | Site process relationships, operating modes, response delays, cross-equipment constraints and permitted SOP steps |
| Deployment | Reviewed industrial host/network placement, identity/certificate rotation, updates, backup, journal retention, recovery and site change control |
| Qualification | Independent software PLC, then isolated hardware bench, then authorised site read-only trial; physical writes only under a site-approved commissioning procedure |

The current read-only OPC UA JSON envelope belongs to the bundled simulator. It is not a generic connector to existing SCADA tags. The current HTTP receiver accepts only a server-configured local simulator address. No code in this release is a drop-in physical plant writer.

## Model output and acknowledgement

The model names an engineering target, not a PLC register:

```json
{"status":"adjust","target":1.0,"rationale":"Residual above objective; make a bounded reduction and observe.","evidence":["chlorine_residual","flow"],"operator_checks":[]}
```

The supervisor adds the captured snapshot, package hash, command ID, expiry, policy and audit evidence. The receiver independently checks that envelope before accepting a target. The UI displays the resulting receipt and readback. A timeout after submission means **unknown**, not “not applied”; reconciliation queries the recorded command ID without replaying it.

For critical states the model can still explain the evidence and name approved operator checks, but cannot obtain automatic actuation. An audit pass cannot override that rule.
