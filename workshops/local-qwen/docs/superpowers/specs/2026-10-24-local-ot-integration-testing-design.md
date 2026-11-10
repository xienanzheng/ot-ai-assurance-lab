# Local OT integration testing — proposed design

Date: 24 October 2026
Status: reviewed design pending user discussion; not implemented or commissioned.
Scope: water first, entirely local simulator/test-bench operation. External systems enter read-only.

Architecture companion: [physical-pilot gaps, open-source shortlist and modular process packages](2026-10-24-physical-pilot-architecture-design.md). This adds proposed qualification milestones and reusable interfaces without enabling external writes or changing the initial water-only implementation boundary.

## Purpose

Prove the complete chain from independently captured measurements to an SOP-grounded recommendation, optional audit, controller acknowledgement and observed process response. Isaac wants a repeatable local exercise, a clear division between human and automated work, and a connector that can later be configured for another HMI/SCADA/PLC system.

Success is an evidence bundle that answers: what did the agent see, why did it propose a change, what was allowed, what did the controller actually accept, and what happened afterwards? A gate pass or an HMI animation alone is insufficient.

This document is a design and ordered testing roadmap. It does not add a service, install software, change deployed models, permit external writes or begin training. A file-by-file implementation plan follows agreement on this design.

## Requirements and design choices

User requirements established in the conversation:

- Local testing with both human exercises and automated checks.
- Persistent acquisition and repeated decisions that respect process response delays.
- SOP and sensor-relationship context, beyond isolated setpoint adjustments.
- Optional audit-before-application; default exercise should work without requiring an audit.
- Concise audit flag reason visible on the recommendation card.
- Reusable integration towards an external PLC/HMI/SCADA.
- Keep the new implementation in a standalone V2 folder, separate from current development. User suggested a simple PLC but has not identified hardware.

Proposed engineering choices, not yet user-agreed:

- Start with a software PLC test bench and a small water process model in standalone V2, using the existing Python/OPC UA approach. No physical PLC or commercial SCADA dependency is required for the first test. This is an engineering default, not a claim that the user selected a particular PLC product.
- Build a separate acquisition/command connector rather than repointing the existing simulator-specific actuator writer at a physical PLC.
- Start external connections in observation-only mode. External physical actuation is outside this iteration.
- Use native Ollama on the development Mac for the offline lane. Resolve and record the installed model; repository defaults are Qwen3 8B, while trained 4B is an unapproved research candidate.
- Audit policies are `off`, `observe`, and `required`. Initial UI defaults to `off`, which means no audit-model request. `observe` preserves today's advisory review. `required` prevents application until a valid review passes. Whether Isaac wants only two UI options remains a presentation choice; all policy values must remain explicit in records.
- No new model training during integration qualification. Use reproducible fake-provider responses for transport tests, then separately evaluate real models.

Unresolved external dependency: no external application, endpoint or PLC make/model has been supplied. This does not prevent local testing. It does prevent promising compatibility with a particular controller.

## Standalone V2 boundary

Planned root is the sibling directory `../water-ot-ai-lab-v2/`, beside `water-ot-ai-lab/` in the fellowship workspace. This design amendment does not create or scaffold that directory yet.

V2 must start, stop, test and reset independently. It must not import V1 modules through relative paths, symlink V1 source, mount V1 runtime storage, call V1 control endpoints or require V1 containers to be running. Reused schemas, water equations or SOP material are copied into V2 with source commit/hash and provenance; subsequent changes are owned by V2. Do not copy credentials, visitor data or unrelated research artifacts.

The first test bench consists of a software PLC running fixed control logic, a water process simulator, an OPC UA interface, the new connector/agent service, its own journal and a minimal HMI. It is a protocol/control test double, not a vendor PLC emulator or IEC 61131-3 certification test. The connector submits supervisory requests; only the software PLC writes simulated actuators.

Use a distinct Compose project (`water-ot-ai-lab-v2`), networks, database, volumes, configuration, evidence directory and start/stop commands. Proposed host ports are loopback-only `18790` for the V2 web UI and optional `18840` for an external local OPC UA client; preflight must check availability and fail clearly rather than displacing another service. Keep internal service ports private. Do not modify V1/Cloudflare routes or startup configuration.

Native Ollama may be reused as an explicitly configured inference endpoint. This is the only proposed shared runtime dependency: V2 must not restart it, change its default model or delete installed models. Record model identity and possible contention; shared inference does not make latency comparisons independent. Test fixtures and protocol checks must also run without Ollama.

Suggested future folders are `services/` (PLC/process/connector/agent/UI), `schemas/`, `profiles/`, `tests/`, `docs/` and ignored `artifacts/`. Exact subdivision is left to implementation planning. This document can be copied into V2 when implementation starts; the current V1 copy records the planning history only. No new repository creation or public publishing is implied.

## What exists now

Code inspected on 24 October:

| Existing component | Current role | Limitation relevant to this iteration |
| --- | --- | --- |
| `services/plant_sim/app/opcua_server.py` | Exposes simulated sensors and writable actuator nodes | Lab-oriented endpoint; not a production security or command-handshake implementation |
| `services/plc_control/app/opc_client.py` | Reads individual nodes and writes actuator values using `asyncua` | Reconnects per operation; assigns simulation time to sensor timestamps; sequential reads do not establish an atomic snapshot |
| `services/plc_control/app/main.py` | Software controller and deterministic proposal/manual endpoints | Application result is not an external PLC acknowledgement protocol |
| `services/supervisor/app/feedback.py` | Budgeted observation and decision loop | In-memory/session lifecycle, simulated time and wall-time cap; not an unattended plant service |
| `services/supervisor/app/decision_auditor.py` | Independent background proposal review | Existing review is advisory; cannot simply be relabelled as blocking |
| `services/web/src/AgentResearchRoom.jsx` | Recommendations and expandable audit reason | Audit reason should become immediately visible without opening details |
| `shared/opcua_nodes.py`, `plant_sops.json`, context book | Tag names, SOP context and timing guidance | Simulator-derived; not a validated physical-site configuration |
| `docker-compose.yml` | Existing local services, PostgreSQL and restart policies | Container restart alone does not recover command/workflow state |

Existing HMI: browser HTTP/WebSocket to supervisor. Existing water control: software PLC reads/writes OPC UA to plant simulator. The proposed connector must not become a second independent actuator writer competing with the software PLC.

## Do we need another application?

The first local run uses the current container runtime, separate V2 test-bench containers, browser and installed model runtime. Models and images must be present before an offline trial. A preflight reports missing dependencies; it does not silently install them or pull model weights. V1 remains an unchanged reference, not a required live dependency.

The new deliverable is a background connector service plus local setup/health controls, not software that watches the screen. It runs while the browser is closed, provided the host remains awake and the service is running.

| Available external interface | Capture approach | First-use restriction |
| --- | --- | --- |
| OPC UA server exposed by PLC or SCADA | Configured monitored-item subscriptions; bounded polling if necessary | Allowlisted read-only nodes, explicit endpoint, certificate/user access configured |
| Supported SCADA/historian API | Vendor-specific read adapter preserving quality and source timestamps | Read only; historian delay is recorded |
| Existing MQTT telemetry | Read permitted topics, validate schema/timestamp/sequence | Broker security and quality semantics require a separate adapter |
| CSV/JSON export | Offline replay adapter with a controllable clock | Cannot claim continuous live control |
| Legacy OPC DA or proprietary interface | Later vendor gateway, potentially Windows-based | Not part of the first Mac-native connector |
| Screen/HMI only, no data interface | Human inspection or screenshots as supplementary evidence | No OCR-derived measurements used to authorize automatic commands |

Do not auto-discover or scan a site network. A plant engineer supplies approved endpoints and tag exports. No extra SCADA purchase is needed to prove the local architecture. An external vendor runtime is selected only once its interface and licensing are known.

## Proposed local components

1. **Acquisition service:** persistent OPC UA session, monitored items, connection health and reconnect handling. A bounded latest-value cache plus timestamped history keeps acquisition independent of model latency.
2. **Site profile:** endpoint identity, namespace URI and stable node identifiers, types, units/scaling, writable capability allowlist, quality/freshness/coherence rules and SOP/topology versions. Credentials/certificates stay outside exported profiles.
3. **Context builder:** combines a coherent measurement snapshot, equipment relationships, selected SOP, previous accepted action and observation state. Missing information remains missing.
4. **Decision scheduler:** triggers from relevant events or scheduled reviews. Limits calls; does not invoke a model for every sensor packet.
5. **Command gateway:** validates proposal, optional audit and current context, then requests a bounded capability from the V2 software controller. It does not bypass the gate or drive raw actuators itself.
6. **Controller-side handshake receiver:** implemented first in the software controller; validates the request, owns deduplication/application and exposes status/readback.
7. **Durable journal:** uses a separate V2 PostgreSQL database for snapshots, commands, acknowledgements, workflow state and observation outcomes. Write intent before submission; never migrate or share V1's live database.
8. **Operator view:** health, latest source age, next review, current mode/owner, pending command, audit reason and actual response trend. The browser is not the scheduler.

Only explicit local simulator/test profiles have a command capability in this iteration. The external connector interface is implemented read-only; UI parameters cannot promote it to a writer.

## Measurement and relationship contract

Each sample records source/profile ID, logical tag, node identity, raw and engineering value, unit, OPC UA StatusCode or mapped quality, source timestamp when available, server timestamp when available, receive timestamp, connection epoch and a local acquisition sequence. Keep source and receipt time separate. Do not make old data fresh by stamping receipt time onto it.

Unchanging values are not automatically stale. Subscription keep-alive confirms connection health, not necessarily instrument freshness. Profile semantics must state how freshness is established: source timestamp, equipment heartbeat or a periodic integrity read. If a required source cannot establish adequate freshness, recommendations can be shown but command eligibility is false.

Build snapshots with per-tag ages and maximum cross-tag skew; OPC UA subscriptions do not guarantee a coherent multi-tag snapshot. The test server provides a snapshot version, read before and after batch acquisition; mismatched versions cause a retry or an explicit incoherent snapshot. External interfaces without this capability must use documented coherence limits and cannot claim atomicity.

Simulation time controls process observation. Monotonic wall time controls communication deadlines. A simulation pause must not expire a process observation window, and an accelerated simulation must not hide wall-time connection failure.

Initial water relationship profile covers disinfection, storage and pressure: equipment connections, measurement locations, input/output dependencies, expected direction of effects, conditions where that direction fails, review delays and SOP prerequisites. It is versioned engineering context, not a learned causal guarantee. The model receives the relevant subset plus the latest trends. Real-site relationships require engineering review against drawings and controls documentation.

## Handshake and control authority

Proposed command states: `created`, `submitted`, `accepted`, `applied`, `observing`, then `completed` or `not_recovered`; alternatives include `rejected`, `expired`, `cancelled` and `unknown`.

- Envelope: command ID, proposal hash, profile/SOP version, controller generation, capability name, validated arguments/units, captured audit policy, issue/expiry times and expected ownership/mode. Audit and gate decisions are attached server-side, never supplied as proof by the model.
- The controller receiver owns a durable deduplication ledger and atomic target acceptance relative to its scan/control lock. A duplicate ID with identical payload returns existing status; same ID with different payload is rejected.
- The simulated receiver can expose a single OPC UA method or structured request with commit semantics. The exact wire representation is left to implementation; independently writable multi-field tags must not permit partially updated commands.
- Submission does not mean acceptance. Acknowledgement must match ID, payload hash and controller generation. Read back accepted targets and observed actuator state separately.
- On timeout, enter `unknown` and reconcile by ID. Do not mint a new ID and resend the same effect. Unknown controller outcome prevents another command for the affected plant.
- Controller restart changes generation. Old requests are rejected; unresolved requests require fresh inspection. Lack of durable controller status never justifies an automatic replay.
- Only one active command/workflow owns the water plant in version one. Multi-equipment parallel ownership is deferred.
- The PLC's existing baseline controller remains the actuator writer. Interlocks, operator mode and critical-state prohibitions stay authoritative. AI does not reset protection.
- If the gate would modify an audited proposal, the resulting proposal is a new hash and requires a fresh audit under `required` policy. No audit pass transfers to changed commands.
- An operator stop disables new submissions immediately. Confirmed cancellation and a completed plant action are distinct; stopping the scheduler cannot undo a physical action already performed.

Transport/acceptance handshake testing uses existing software endpoints first and the simulated receiver's OPC UA boundary next. Physical PLC-side function blocks are a later vendor-specific deliverable, not generated portable executable PLC logic.

## Audit and monitoring policy

`off`: skip the audit call; retain deterministic gate checks. `observe`: background review has no actuation authority. `required`: obtain a valid pass for the exact proposal before applying; pending, flagged or unavailable prevents the new command. Show one short supported reason on the card and expandable evidence.

Capture policy per decision. Changing the setting affects subsequent analyses. Never silently release a previously blocked proposal. A critical transition, operator mode change or controller restart while an audit/model is running invalidates eligibility. Recheck under the controller's application lock after inference/audit.

For the first version, monitoring restarts automatically but **control does not re-arm automatically after a process/service restart**. Resume telemetry, reconcile pending commands and show the operator what happened; a deliberate local arm action is required for new writes.

Use debounced event triggers, periodic review and a minimum observation period per applied action. Critical/invalid-data events interrupt waiting and inhibit commands immediately; response review does not wait for an LLM to announce a protection issue. A warm model may stay loaded, but the acquisition service must continue collecting when inference is slow or unavailable.

The first autonomous endurance trial is bounded to a documented test duration and inference budget. Budget exhaustion changes to observation-only; it does not stop telemetry or remove PLC protection. No uncapped API spending or background collection from visitors.

## Step-by-step human and automated test sequence

Advance only when the stated evidence exists. These are local engineering checks, not certification or a general model-accuracy benchmark.

| Stage | Human actions | Code actions | Evidence / exit condition |
| --- | --- | --- | --- |
| 0. Inventory and freeze | Confirm local machine, V2 test profile, available models and selected water exercises; label intended cloud/offline lane | Report versions, health, hashes and model identity; check port/storage isolation; record baseline controller behaviour | Reproducible run manifest; V2 runs with V1 stopped; no hidden provider fallback; no new installs without need |
| 1. Capture only | Start lab; inspect normal readings; change one simulator input; compare source and HMI | Collect read-only samples; retain units, quality and times; prohibit command submission | Every configured tag maps correctly; normalized readings agree with source within declared precision; zero command calls |
| 2. Bad data and reconnect | Pause/disconnect test source; restore it; inspect quality display | Inject missing, stale, future, bad-quality, out-of-order, unit and scaling errors; detect incoherent snapshots and subscription gaps | No invalid snapshot eligible for command; no silent data-gap filling; fresh coherent data required after reconnect |
| 3. SOP shadow analysis | Select a normal, warning and critical case; review concise evidence and next step | Replay frozen snapshots through fake provider, then installed Qwen; attach SOP and topology versions | No actuation; distinguish hold/adjust/escalate and unsupported diagnosis; retain all model failures |
| 4. Handshake without process writes | Inspect request and acknowledgement IDs; interrupt connection between them | Test receiver in dry-run; duplicate, mismatched, expired, rejected, delayed and lost acknowledgements; restart gateway/controller | Same command never accepted twice; uncertain result stays unknown; no target changes in dry-run |
| 5. One supervised simulator action | Arm local test profile; explicitly request one permitted adjustment; inspect HMI target and feedback | Pass gate, submit to receiver, confirm acceptance/readback, observe response | One accepted command; old/new targets and actual response recorded separately; no early recovery claim |
| 6. Optional audit | Repeat the same frozen cases with off, observe and required modes | Test pass, flag, timeout, malformed review, changed proposal and policy changes in flight | Off causes zero audit requests; required never submits without a valid matching pass; one-line reason visible |
| 7. Feedback and process delay | Run selectable chlorine adjustment, storage and pressure exercises; trigger an operator takeover | Continue acquisition; reassess only after configured window unless protection intervenes; record other affected sensors | No stacked commands during wait; takeover stops new commands; sustained/no/poor response distinguished |
| 8. Endurance and recovery | Close browser; run a 60-minute real-time local test; restart services; separately sleep/wake host | Heartbeats, bounded buffers, reconnect/backoff, persistence, pending-command reconciliation and budget handling | Browser closure has no effect; gaps recorded; restart resumes observation only; no duplicate or spontaneous commands |
| 9. Other application, read-only | Obtain approved endpoint/tag list and access; compare several readings in vendor HMI | Configure profile and permitted connector; compare live stream and quality/timestamps with source | Tag mapping and acquisition compatibility report; zero external writes; any unsupported interface explicitly listed |

Stage 8 uses a maximum 12 decision calls as a proposed local test budget, with a configurable review schedule constrained by the SOP window. This is a qualification run, not the final plant operating policy. At least one real-time run is required; accelerated simulation complements rather than replaces it. Host sleep causes a collection gap; a Mac laptop cannot promise uninterrupted acquisition while asleep.

Initial scenario pack: normal hold; bounded noncritical chlorine correction; observation-window hold; critical alarm/escalation; stale required sensor; missing flow proof; latched trip; command/feedback mismatch; slow response; no response; operator takeover; connection loss. Extend storage/pressure only after disinfection capture/handshake checks pass. Nuclear and grid are later extensions.

## Separate infrastructure correctness from model usefulness

Use deterministic fixture proposals to test connector, gate and handshake invariants. Those tests must pass even with a consistently wrong or unavailable model. Then run the same versioned scenario episodes using real local models and optionally cloud providers as a separately labelled connected lane.

For model outcomes, preserve proposed versus applied actions, escalation appropriateness, supported SOP references, correct holds, observation timing, response trajectory and recovery persistence. Compare baseline-controller-only runs with AI runs using matched initial states/disturbances. A gate blocking bad proposals does not make those proposals correct. Do not claim improvements from one favourable run.

The older 400-case study is development evidence and is not reused as new independent evidence. The 1,000-case locked test is not opened or repurposed by this integration work. Do not train on test-session records automatically.

## Deliverables and suggested code boundaries

- Design-approved implementation plan and human runbook with exact local commands, expected screens, stop/recovery actions and evidence paths.
- Separate connector package using the existing Python stack; configurable read-only external profile and simulator-only command adapter.
- Versioned schemas for measurements, plant relationships, command envelope, acknowledgement and outcome.
- New receiver/journal in the V2 software controller; no V1 database migration.
- Restart-aware supervisor scheduler plus audit policy integration across manual apply, comparison selection and feedback. Legacy control paths must either obey the policy or explicitly lack command authority in the new profile.
- Setup/health page in a minimal V2 frontend using the existing React approach; no changes to V1 frontend and no separate desktop GUI framework required.
- Fake OPC UA/receiver fault fixtures, deterministic integration tests and real-model scenario reports.
- Session exports with JSON/CSV: profile/config hashes, sensor samples and gaps, exact model inputs/outputs, audit evidence, gate reasons, request/ack/readback, observed trajectories and human interventions. Never include secrets or private keys.

Reuse the `asyncua`, FastAPI, React and PostgreSQL technology choices in V2. Exact module names, queue sizes and test-helper organisation are left to the builder. Introduce no new infrastructure dependency without explaining the need. Retention and deletion are explicit profile settings; the initial local test retains its bounded run bundle until manually deleted. Reset/cleanup commands must target V2 resources exclusively.

## Physical-site boundary

No claim of ready-to-install physical control. A later site phase needs an approved architecture, correct tag/unit mapping, certificates and roles, a PLC-side handshake implementation, plant-specific SOPs/limits/delays, agreed fallback behaviour and commissioning tests with responsible engineers. Do not carry the simulator's writable anonymous nodes or global time-as-sensor-age convention into a physical deployment.

The connector can be installed on an approved edge host rather than on the HMI workstation. Whether it can run on the same machine depends on vendor support and site permissions. An air-gapped profile uses locally provisioned models and dependencies; Qwen Cloud and Jev API require a distinct connected profile. Test the offline profile with outbound access blocked and verify no hidden cloud fallback or telemetry export.

## Sources

- Existing repo: `docker-compose.yml`, `services/plant_sim/app/opcua_server.py`, `services/plc_control/app/opc_client.py`, `services/plc_control/app/main.py`, `services/supervisor/app/feedback.py`, `services/supervisor/app/agents.py`, `docs/DECISION_AUDIT.md`, `docs/PLANT_CONTEXT_BOOK.md`.
- OPC Foundation subscription model: https://reference.opcfoundation.org/specs/OPC-10000-4/5.14.1
- OPC Foundation DataValue: https://reference.opcfoundation.org/specs/OPC-10000-4/7.11
- OPC Foundation security model: https://reference.opcfoundation.org/specs/OPC-10000-2/4

These specifications describe transport and data semantics, not a certified AI control architecture.

## Design review

A fresh builder review on 24 October returned “nothing important left” for planning the local test-bench and external read-only scope. This was a design completeness check, not execution, code verification or physical-site approval. The external application/PLC identity remains an explicit prerequisite for stage 9 configuration.

User follow-up on 24 October specified standalone V2 and suggested a simple PLC. The isolation requirements above reflect that follow-up; the software PLC starting point is the assistant's proposed default pending hardware selection.

The builder rechecked the standalone V2 amendment and again returned “nothing important left” for implementation planning within this scope.
