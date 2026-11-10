# From simulation lab to physical pilot — architecture review

Date: 24 October 2026. Status: researched proposal; no installation, hardware commissioning or physical writes performed.

Companion to [the standalone V2 local-testing design](2026-10-24-local-ot-integration-testing-design.md). That design remains the implementation boundary: local simulator commands and external read-only capture. This document adds a roadmap towards a physical pilot; it does not extend V2's initial write permissions.

## Architectural judgement

Our lab provides a useful place to study model proposals, SOP context, gates and process outcomes. The next engineering challenge is making the complete control chain dependable when data, communications, software or people behave unexpectedly. A better model alone cannot establish that dependability.

The existing plan already addresses timestamps, quality, snapshots, deduplication, command acknowledgement, observation delays, operator takeover and restart recovery. The largest additions needed are an independently implemented controller boundary, a validated site configuration, physical I/O testing, process-specific fallback, and a commissioning/maintenance package.

Recommendation: retain the current Python stack, qualify one small water loop, then add an independent PLC runtime and a disconnected hardware bench. Chemical dosing stays simulated initially. A first physical experiment should use a contained, low-energy water-level rig or electrical I/O simulator, selected and assembled with a controls engineer. Nuclear and grid remain simulation-only in this roadmap.

These are the assistant's proposed choices. The user requested standalone V2 and suggested a simple PLC; no hardware, site or vendor has been selected.

## Where the components belong

The background connector belongs on an approved local edge host. It reads an explicitly configured PLC, SCADA data server or historian interface. It does not scrape HMI pixels or require installation on the operator's workstation. The HMI displays measurements, ownership and acknowledgements; it is not proof that a command reached equipment.

```text
FIELD / EXISTING CONTROL                 LOCAL EDGE
Sensors --> PLC --> Actuators            Acquisition --> validated snapshot
             |                                 |             + SOP/topology
             +--> Existing HMI                 |                  |
             |                                 |             Local Qwen
             +-- approved telemetry ---------->+                  |
             |                                                proposal
             |                                                    |
             |                                      optional model audit
             |                                                    |
             |                                      independent command gate
             |                                                    |
             +<-- scoped request -- PLC receiver <--- command gateway
             |       (future physical pilot only)
             +-- acknowledgement / readback --> journal --> outcome monitor

Operator authority and existing protection remain outside model control.
Public Cloudflare demo has no route to this control path.
```

The local model is a supervisory decision aid, operating at an engineering-defined review interval. PLC scan logic, PID loops and protective functions continue independently of inference. Their timing requirements determine when a proposal is too late; the model's inference speed does not define the control deadline.

An offline deployment uses local inference, locally provisioned dependencies and approved offline updates. Cloud Qwen/Jev are a separate connected research lane. Do not connect an isolated plant to a hosted provider by reusing the public demo or a Cloudflare Tunnel.

## Gaps to close, with evidence

All rows below are proposed requirements, not claims of existing implementation or legal certification.

| Gap beyond the present local plan | Required addition | Evidence before advancing | Responsible role |
| --- | --- | --- | --- |
| Site meaning and configuration drift | Verified tag dictionary, engineering units, sensor location, topology, valve direction, PLC firmware/program identity and profile revision | Every required tag checked against source; mismatched profile/program version inhibits commands | Controls engineer + integration developer |
| Physical measurement integrity | Calibration status, uncertainty, filtering, sample-line/transport delay and independent reference measurements | Bench captures distinguish instrument lag, actuator movement and process response; disagreement prevents an unsupported correction | Instrumentation/process engineer |
| Command authority outside our application | PLC-side allowlisted capabilities, local enable, owner/epoch, expiry and final permissive checks | Operator takeover wins; forged, stale, duplicate or concurrent requests cannot obtain authority | PLC engineer |
| More than simple min/max bounds | Rate-of-change and cumulative-change limits, dwell times, sequence prerequisites, coupled constraints and a feasible operating envelope | Several individually legal proposals cannot accumulate into a prohibited change; waiting and infeasible objectives produce hold/escalation | Process + controls engineers |
| Failure after an accepted change | Defined behaviour for lease expiry, model outage, gateway crash, power loss and failed actuator feedback | Tests show agreed fallback and transfer to baseline without an unintended target jump | Controls engineer + operator |
| Independent physics and ground truth | Cross-check selected scenarios against a second model and later measured bench trajectories | Conservation, effect direction, settling behaviour and uncertainty reviewed independently of the model's answer | Process/modelling engineer |
| Physical and network boundary | Separate service identities, restricted protocols/nodes, trusted certificates, local credentials and resource limits | Read role cannot write; expired/untrusted certificates fail; model process has neither PLC credentials nor direct network access | OT security + integration developer |
| Unattended operation | Power/thermal/storage sizing, service watchdog, bounded queues, disk policy, clock monitoring and restore procedure | Long real-time run, resource exhaustion, offline boot and recovery drills; local control survives AI-service failure | Platform engineer |
| Human authority and usable alarms | Roles for view/propose/approve/arm/configure; concise reasons; shift handover and change log | Operator can identify pending versus applied action, disable future AI requests and recover without the AI UI | Operations lead |
| Controlled releases and maintenance | Pinned software/model/SOP versions, dependency inventory, artifact integrity checks, backups and rollback | Clean offline installation and tested rollback to a known configuration; no automatic model/SOP promotion | Release owner + site owner |

NIST's OT guide supports treating performance, reliability and safety together. Its network and failure-handling sections inform this review; the concrete tests and allocation of responsibilities above are our proposed design. [NIST SP 800-82 Rev. 3, §§5.2.3 and 5.3](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-82r3.pdf). The official page now links a Revision 4 initial public draft; it is not treated here as a final replacement. [Publication status](https://csrc.nist.gov/pubs/sp/800/82/r3/final).

## Open-source shortlist: use only where it closes a gap

Source capabilities and top-level licence labels checked on 24 October 2026. These are candidates, not installed or interoperability-tested components. Freeze actual release hashes and inspect dependency licences at implementation time.

| Component | Verified capability / licence | Proposed role | Decision and limitation |
| --- | --- | --- | --- |
| [asyncua](https://github.com/FreeOpcUa/opcua-asyncio) | Python OPC UA client/server, subscriptions, methods and certificate/encryption support; LGPL-3.0 | V2 acquisition and simulator protocol adapter | **Retain.** It fits our current stack. Application reconnect, quality semantics, permissions and recovery still require explicit tests. A library feature is not a commissioned security configuration. |
| [OpenPLC Runtime v4](https://github.com/Autonomy-Logic/openplc-runtime) | Executes Editor programs using IEC 61131-3 languages; Docker runtime with listed ARM64/AMD64 builds; MIT | Independently implemented soft-PLC target after our deterministic test double | **Evaluate next.** Verify the chosen release's data interface and receiver feasibility first. The inspected README does not establish a native OPC UA interface. Do not assume our connector plugs straight into it. A Mac container is not a physical real-time timing test. |
| [Eclipse Milo](https://github.com/eclipse-milo/milo) | Java OPC UA client/server SDKs; EPL-2.0 | Independent OPC UA interoperability test fixture | **Optional test dependency.** Helps expose assumptions hidden when both endpoints use asyncua. It does not replace the controller or add safety authority. Use pinned release features, not snapshot-only features. |
| [Fledge](https://github.com/fledge-iot/fledge) | Linux industrial edge gateway with protocol plugins, buffering and historian integration; Apache-2.0 | Capture gateway when a partner has several data sources | **Defer until needed.** Qualify each plugin's timestamp, quality and permissions behaviour. Do not add it beside asyncua just to increase the stack, or use its control features to bypass our gateway. |
| [WNTR](https://github.com/USEPA/WNTR) / [EPANET](https://www.epa.gov/water-research/epanet) | Water-distribution hydraulics and quality tools; WNTR Revised BSD, EPA EPANET public domain | Independent scenario reference for storage, pressure and distribution transport | **Add to evaluation, outside the live command path.** Distribution models do not validate every treatment process or rapid transient. Field calibration remains necessary. |

WNTR's `WNTRSimulator` handles hydraulics; its EPANET-based path handles water-quality simulations. Choose the engine explicitly rather than assuming either predicts chlorine transport. [Hydraulic documentation](https://usepa.github.io/WNTR/hydraulics.html), [water-quality documentation](https://usepa.github.io/WNTR/waterquality.html).

The default first build stays asyncua + existing Python/React/PostgreSQL choices. OpenPLC has a feasibility checkpoint, not an unconditional dependency. If its selected release lacks a suitable interface, retain the local test double and qualify a documented adapter or another controller target; do not silently substitute raw register writes. MQTT, a fleet-management platform, a new SCADA system and Kubernetes are not prerequisites for one local bench.

## Modular adoption: water, cooling and manufacturing

User follow-up: make the architecture reusable through modules/plugins for another manufacturing step or cooling system. This changes how we divide V2, not the initial permission to actuate external systems.

**Design principle: reusable runtime + protocol adapters + process packages + site bindings.** Connecting a new interface and understanding a new process are separate jobs. A cooling package must not inherit water-treatment limits because both contain pumps.

| Module | Stable responsibility | What changes for a new process/site |
| --- | --- | --- |
| Telemetry adapter | Read/subscribe, report quality/time/identity and connection health | Protocol implementation if unsupported; otherwise endpoint and tag bindings |
| Normalisation and snapshot service | Validate types/units, preserve provenance, freshness and coherence | Per-tag scaling, acceptable age/skew and required sensor groups |
| Process package | Describe assets, dependencies, operating modes, SOP/check IDs and response expectations | Water/cooling/manufacturing semantics and scenario fixtures |
| Model provider | Render supported request, invoke model, validate/normalise response | Local Qwen/cloud Qwen/Jev adapter; provider-specific typed-choice versus generation interface |
| Audit provider | Return pass/flag/unavailable, supported reason and evidence references for an exact proposal | Reviewer model and configuration; never command authority |
| Policy engine | Enforce non-bypassable authority, schema, age, ownership and lifecycle rules | Reviewed domain constraints supplied as a versioned policy package |
| Command adapter / receiver | Map an allowed capability to a controller request; reconcile status/readback | PLC interface and approved capability mapping; physically separate from telemetry permissions |
| Scheduler and outcome monitor | Event/periodic review, observation windows, lifecycle and result journal | Review rules, response sensors, expected direction, duration and success criteria |
| Operator UI and exports | Display units, trends, proposal, audit reason, gate/receiver state and outcomes | Labels, sensor groups and optional domain schematic; no embedded safety logic |

Keep these as explicit package interfaces, not nine new microservices. Initially use a small number of processes: protocol/receiver boundary, agent/supervisor, storage and UI. Isolate inference from control credentials and resources; further deployment separation follows site requirements. No runtime dependency on V1.

### Process template versus site instance

A reusable **equipment template** describes a pump, valve, level sensor or heat exchanger. A **process package** composes equipment into a specific kind of operation and supplies its SOPs and approved capabilities. A **site binding** instantiates that package with actual tag identities, capacities, reviewed limits, delays and controller mapping. Version all three independently and record the resolved combination in every run.

Prefer existing OPC UA identity and device concepts where the source exposes them. OPC UA for Machinery provides reusable identification building blocks, while Devices provides a way to organise parameters and methods. These help interoperability; they do not supply a plant's SOP, causal model or command permissions. [Machinery use cases](https://reference.opcfoundation.org/specs/OPC-40001-1/5), [Devices model](https://reference.opcfoundation.org/specs/OPC-10000-100/full).

Examples below are illustrative packages, not implemented or approved physical operating procedures:

| Package | Input context | Example restricted capability | Outcome evidence and prerequisites |
| --- | --- | --- | --- |
| Water storage | Level, inflow/outflow, pump/valve feedback, operating mode | Request a bounded storage target | Net-flow direction, level trajectory and other storage constraints; sensor validity and controller permission |
| Cooling loop | Supply/return temperature, flow, thermal load estimate, pump/fan feedback and equipment alarms | Request a bounded cooling target | Temperature response after thermal delay; adequate flow and equipment operating envelope; include freeze/condensation constraints where applicable |
| Manufacturing step | Step/recipe revision, machine state, material presence, quality result and upstream/downstream readiness | Request an approved parameter adjustment within the active recipe | Correct step and material identity, machine permissives, quality response and downstream availability; no arbitrary sequence start or protection reset |

The reusable part is the request/evidence lifecycle. Cooling needs thermal relationships and a different time response; a manufacturing step needs sequence/material state and recipe authority. A manufacturer-specific protocol or a new executable workflow can require new reviewed code. Supported equipment with an existing adapter may need only a new site binding and qualification tests. No promise of zero engineering effort.

### Contracts and plugin admission

Use versioned typed contracts for `Measurement`, `Snapshot`, `ProcessContext`, `Proposal`, `AuditResult`, `GateResult`, `CommandRequest`, `CommandStatus` and `ObservedOutcome`. Every proposal binds to asset/site identity, snapshot identity, capability version and the applicable configuration hashes. Transport-specific addresses stay inside adapters. Models may reference only capabilities and evidence present in their captured context.

A package manifest declares its ID/version, compatible contract versions, dependencies, required observations, offered capabilities, permission class (`read_only` or `simulated_control` initially), configuration schema and test-fixture inventory. The runtime rejects incompatible contracts, missing mandatory measurements, conflicting capabilities and unresolved unit conversions before enabling a run. A typed numeric value without the required unit/measurement location is insufficient.

Separate data packages from executable plugins. SOPs and tag maps are validated data, with no embedded Python, shell, SQL or unrestricted expressions. Deterministic constraints use a limited supported rule vocabulary; a new constraint requiring code is a reviewed extension, not model-generated executable text. Executable adapters are administrator-installed from pinned, verified bundles; do not load code URLs, paths or uploaded plugins from browser requests. Hashes establish identity; trust comes from an approved publisher/review process.

Only the gateway's command identity can request a write, and only the receiver can accept it. Telemetry/model/audit plugins cannot obtain that identity or alter policy. A plugin timeout or crash marks its required output unavailable and inhibits dependent commands; it does not silently substitute another provider or fill required measurements with defaults.

No hot swapping during an active workflow. Drain or stop decision submission, reconcile pending commands, load/validate the new package, then explicitly re-arm. Changing a tag map, model, SOP, capability or policy produces a new versioned run context. Existing records keep their original versions and remain readable. Multi-process/asset command concurrency stays deferred: V2 first supports one active controlled process; equipment templates do not imply independent parallel write authority.

### Prove modularity rather than naming folders

After the water loop works, introduce a **simulated cooling-loop package** as a portability test. It must reuse the same acquisition contract, scheduler, audit modes, gate lifecycle, receiver handshake, journal and generic UI. Only the process package, bindings, plant simulator and optional schematic should change. This is a later local milestone; it does not postpone the initial water test or enable a physical cooling system.

Acceptance checks:

1. A new instance of a supported process needs no edits to core Python or UI logic; the configuration validates and supplies display metadata.
2. Cooling can run without water-only sensor IDs, chlorine rules or water prompt text leaking into its context. A missing required thermal sensor prevents command eligibility.
3. Both packages pass the same contract/fault suite: wrong units, bad quality, stale data, incompatible version, duplicate command, unknown outcome, audit flag, takeover and restart.
4. Unsupported capabilities, unapproved executable packages and cross-site proposals are rejected. An export cannot replay itself into another site.
5. Provider swaps preserve the canonical proposal contract while recording differences in model inputs and typed-choice assistance. No claim of identical model evaluation conditions follows from a common interface.
6. Domain-specific scenarios validate response timing and outcomes separately. Passing the common adapter suite does not validate the new process physics.

Suggested future layout: `core/`, `contracts/`, `adapters/telemetry/`, `adapters/commands/`, `providers/`, `process_packages/`, `site_profiles/`, `tests/contracts/` and `tests/scenarios/`. These are proposed boundaries; the implementation plan can simplify names. No plugin framework or new package registry needs to be installed now.

## Three contracts that need more precision

### 1. SOP recommendation is different from an executable procedure

An SOP paragraph can justify a recommendation, but cannot safely become an arbitrary sequence of model-generated commands. Split the site package into:

- **Reviewed operational text:** purpose, symptoms, checks and operator responsibilities.
- **Machine-checked capability rules:** required measurements, modes, bounds, ramp/dwell limits, expiry and failure behaviour.
- **Approved workflows, later:** fixed ordered steps, required feedback at each step, timeout/abort points and manual hold points. The model may recommend an approved workflow; it cannot invent PLC code or skip a step.

First V2 supports one bounded target change followed by observation. Multi-step procedures are a later scope. Critical-state output remains evidence and operator checks with no automated recovery/reset. Model audits may be off/observe/required in the lab; a site deployment fixes that policy through engineering change control, not an unrestricted visitor toggle. An audit pass never substitutes for the deterministic checks.

SOP retrieval supplies context; it is not weight training. Keep curated source versions, author/reviewer and validity scope. Retrieved text is data: text asking to bypass a protection cannot change gateway policy. Plant data and model output cannot write the policy, credentials or approved SOP store. Unrecognised operating conditions produce a hold/escalation with the missing evidence identified.

### 2. JSON is a request, not control authority

Models select known capability names and bounded arguments. They do not receive writable node addresses, arbitrary register numbers, PLC credentials or a code-execution tool. Server-side validation creates the command envelope; the gateway maps a capability to the approved controller interface.

The future receiver checks current mode, ownership token, profile revision, age and permissives at acceptance. It returns command identity, accepted/rejected state and a reason code. Requested target, accepted target, actuator feedback and measured process response remain separate records.

Keep the existing V2 deduplication and unknown-outcome rules. Add crash tests between journal write, acceptance, actuation and acknowledgement. A durable journal cannot make a physical action and a database commit one atomic transaction. After ambiguous power loss, inhibit new requests and reconcile; do not claim exactly-once physical execution. Repeated pulse/sequence actions are outside the first capability set.

For a simple PLC with limited persistent storage, qualify a receiver mailbox/sequence scheme and restart generation with its controls engineer. If reliable reconciliation cannot be provided, that controller remains observation-only for this integration. An adapter cannot manufacture acknowledgement semantics absent from the PLC.

### 3. Recovery must be observed against an agreed objective

Each capability needs predeclared measurable response criteria: relevant sensors, expected direction, allowed delay, minimum observation interval, sustained success window, prohibited side effects and maximum episode duration. Values come from the bench model first, then reviewed site information; do not transplant demo chlorine thresholds or accelerated-time settings into a plant.

Include wrong-way response, no response, saturation, hysteresis, sensor drift and competing demand. If the command is acknowledged but feedback fails, stop issuing compensating guesses. An unreachable objective should be recognised rather than chased with accumulating adjustments. Site-defined fallback may hold a target, transfer to a baseline regulator or stop a sequence; it is not universally “close every valve” or “restore the old value.”

Measure time to command acknowledgement separately from time to process recovery. Freeze input disturbances and compare controller-only versus AI-assisted episodes. Report constraint violations, false interventions, missed interventions, time within objective, actuator wear proxies and operator workload. Report energy or chemical savings only where quantities are actually measured or explicitly modelled. Hidden future measurements and expected answers must not enter the model prompt.

## Site package: what would travel with the application

The proposed product is an edge application plus a reviewed site package. It is not a universal installer that discovers a plant and starts controlling it.

| Package item | Content / validation |
| --- | --- |
| `site-manifest` | Asset IDs, drawings/control-narrative references, responsible owners, approved environment and revision identities |
| `tag-map` | Endpoint, namespace URI/node identity, units/scaling, source freshness and quality semantics, location and calibration reference |
| `capabilities` | Allowed requests, modes, limits, cumulative/rate constraints, receiver mapping and confirmation rules |
| `relationships` | Equipment graph, upstream/downstream effects, measured delays and exceptions; engineering review record |
| `sop-catalog` | Approved instructions/check IDs, source revision and applicable states; model-accessible subset |
| `fallback-matrix` | Failure condition → controller/operator action, ownership and recovery prerequisites |
| `acceptance-pack` | Frozen test cases, test tolerances, commissioning results, rollback and operator runbook |
| `release-manifest` | Code/model/runtime/schema/SOP hashes, dependency inventory, licence notices and supported restore version |

Names describe future artifacts, not created files. Secrets and private keys are provisioned separately. Do not copy site data to the public repository or train on it automatically. Retention, export approval and log access are site decisions. For the small lab, an append-only application journal and bounded exports suffice; production evidence needs access controls, backups and integrity verification appropriate to the site.

## Physical bench and edge-host readiness

Before buying a PLC, record its supported protocol, read/write licensing, program tool/OS, available I/O, retained-memory behaviour, method/structured-write support and scan/watchdog capabilities. Check whether a Linux VM/container on the Mac can run the tools; do not assume a vendor's engineering software supports macOS. Inspect the exact product documentation once a device is identified.

Start hardware-in-the-loop with a PLC connected to simulated I/O. A later water rig needs engineer-selected low-energy components, independent high/low-level protection, containment, physical stop/local selection and proper electrical isolation. Do not buy a dosing pump or connect utility equipment for this first milestone. No wiring instructions or real-site control values are inferred from the simulator.

The edge host needs a supported OS, measured inference memory/thermal headroom, reliable storage, appropriate power protection and a restricted management path. Keep inference resource limits separate from acquisition and gateway resources. If the model crashes or exhausts memory, the PLC continues its existing control and the connector reports loss of advisory service. Hardware sizing comes from measured full-context latency and retention volume, not parameter count alone.

A cold, fully offline boot must succeed with preloaded artifacts. Test trust/certificate expiry, clock jumps, disk full and backup restore. Do not equate Docker restart policies or a 60-minute laptop run with unattended availability. High availability is deferred; if later introduced, controller-enforced ownership fencing must prevent two edge nodes from writing simultaneously.

## Staged roadmap and release conditions

| Stage | Added scope | Exit evidence |
| --- | --- | --- |
| A. Standalone V2 | Existing proposed local bench, persistent capture, gate, journal and monitoring | All original stages 0–8 pass, including bad data, lost acknowledgements, takeover and restart; V1 remains independent |
| B. Independent implementations | Qualify a soft PLC/interface and cross-stack OPC UA tests; selected water-model cross-checks | Tested version/interface matrix; no reliance on two ends sharing the same bug; documented process-model limitations |
| C. Disconnected hardware bench | Real PLC and simulated I/O, then an engineered water-level rig | Point-to-point I/O checks, ownership/stop/fallback tests, actuator feedback and measured response; no connection to utility assets |
| D. Site read-only shadow | Approved edge host, restricted data identity, reviewed tag/site package | Accurate capture with acceptable source load; recommendations reviewed by operators; no physical write credentials or command route |
| E. Supervised site pilot | Separate approved scope and vendor-specific receiver; one noncritical capability | Process-risk review, acceptance tests, named operator, change window, independent protection and tested rollback; every initial action deliberately authorised |

Stage E is not authorised by the current request. Stages A–D do not imply site readiness for actuation. A site's engineering/safety/security owners determine applicable standards and sign-off requirements; no generic research benchmark can replace that work.

Keep the 60-minute test as an early check. Before stage D, proposed endurance qualification is 24 hours at real time with representative telemetry volume and injected service/network/storage failures; longer coverage and tolerances are agreed for the target site. Required pass conditions include zero out-of-authority commands, preserved baseline control, detectable data gaps, consistent command accounting and usable operator recovery. Freeze timing tolerances before execution rather than choosing them after observing results.

Model selection remains separate. Current fine-tuned Qwen evidence includes failed acceptance criteria, so a training gain is not a physical-control qualification. Use deterministic test proposals for infrastructure proof and real models for independent usefulness evaluation. Retain failures and report denominator counts; do not hide them behind gate rejection rates.

## Next deliverables, in order

1. Incorporate this review into the V2 implementation plan: capability/schema contracts, one loop, fault fixtures and human runbook first.
2. Create the standalone V2 folder only when implementation begins; no runtime imports or control coupling to V1.
3. Qualify the open-source PLC interface in an isolated feasibility test before committing to it; record platform, release, protocol and limitations.
4. Produce an empty site-package template and a filled simulated example, with no real plant credentials or invented engineering approvals.
5. Produce a bench acceptance report before hardware/site expansion; retain a clear distinction between implemented, tested and proposed features.

No hardware choice is needed to plan stage A. Before stages C/D, the material inputs are the actual PLC/interface, permitted test environment, plant documents and responsible controls/process/operations contacts. Those cannot be deduced from the web application.

## Review record

A fresh independent OT integration/modular-software builder check on 24 October returned “nothing important left” for planning the scoped local V2 and later simulated cooling portability test. The unspecified physical site's engineering decisions remain explicit prerequisites for later stages. This was a design completeness check, not certification or executed testing.
