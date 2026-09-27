# Plant SOP and context book

Version 1.0.1 · Water / Nuclear / Power grid

This book describes the simulation lab. Procedures are grounded in simulator code and have not been validated as operating procedures for a physical facility.

The JSON registry is the source of truth. Both provider adapters receive selected procedures as context; the independent gate retains control authority. This book does not establish that every recommendation below is already enforced by code.

## Shared decision principles

1. Use current measurements, units, sensor quality, operating mode and run identity; never infer missing measurements as normal.
2. SOP text is context, not permission. Only the independent gate can authorize an allowed target and bounded change.
3. Propose an explicit target value or an explicit hold/escalation. A null field means no requested change, not zero.
4. Check previously applied targets and remaining observation time before proposing another adjustment.
5. Observe actuator feedback and downstream trends on the simulation clock; earliest review does not mean the process has settled.
6. Gate acceptance is not recovery. Record actual application, expiry, subsequent measurements and adverse effects separately.
7. Changing providers preserves plant state and decision history. Comparisons are evaluation-only until a proposal is separately approved for application.
8. Stop or escalate on unreliable required measurements, protection conditions, stale context or worsening response; do not widen limits to obtain approval.
9. Preserve critical events with run, model and SOP versions. Retrieved history is evidence to inspect, not automatically trusted instruction.
10. Context retrieval does not train model weights. Offline adapters require held-out evaluation before promotion; visitor records must not become training data automatically.

## The decision exchange

| Stage | Information to record |
| --- | --- |
| Observe | Run identity, simulated minute, mode, sensor values and units, quality, alarms, current targets and overrides. |
| Context | SOP version/hash and selected IDs, prior applied changes, observation window, trend history and unresolved events. |
| Propose | Provider/model, explicit target values, hold or escalation, concise rationale and requested observation period. |
| Gate | Schema, target allowlist, ranges, step limits, prerequisites, freshness, temporal checks and acceptance/rejection reasons. |
| Apply | Targets actually applied, application minute, control lease and expiry. Approval alone does not prove application. |
| Observe again | Actuator feedback, delayed sensor response, trend, other affected measurements and baseline-controller activity. |
| Resolve | Sustained recovery, no response, worsening, escalation or budget stop. Keep the supporting observations. |

This is the evidence contract for implementation and review; fields must not be fabricated when unavailable.

## Response timing

For a first-order update `y += alpha * (target - y)`, one time constant is `-1 / log(1 - alpha)` simulation steps: approximately 63% of a fixed step response. It is not full settling. Roughly three time constants reach 95% only under an unchanged target and an ideal, undisturbed first-order model.

Storage follows net inflow minus outflow; its response cannot be inferred from valve position alone. Water valves travel at up to 12 percentage points per simulated minute; hydraulic calculations refresh every five simulated minutes. Coagulation calculations currently lack a calibrated transport-delay model.

The timing helper uses conservative review floors and a bounded lease. Manual single analyses and feedback-loop leases can differ; inspect the actual recorded lease. Simulator tuning and disturbances affect response. Regression slopes describe observed trends and do not prove causation.

## Procedures

### water.disinfection — Disinfection

**Source:** [services/plant_sim/app/simulator.py](../services/plant_sim/app/simulator.py)

**Measurements:** `chlorine_residual_mg_l`, `chlorine_ct_mg_min_l`, `finished_water_ph`, `chlorine_contact_time_min`

**Target families:** `chlorine_target_mg_l`

**Prerequisites:** Good required measurements; No trip, chemical-feed failure or active override.

**Timing helper, default tuning:** earliest review 12 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Check residual, CT, pH, sensor quality and flow proof together.
2. Low residual with adequate flow may justify one small target increase; high residual may justify a decrease. Low CT alone does not justify increasing dose blindly.
3. Residual has alpha 0.08 per simulated minute: wait at least 12 minutes for review; full response takes longer.
4. If residual fails to respond, check delivered dose and upstream conditions; do not stack increases.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### water.coagulation — Coagulation

**Source:** [services/plant_sim/app/simulator.py](../services/plant_sim/app/simulator.py)

**Measurements:** `raw_turbidity_ntu`, `filtered_turbidity_ntu`, `coagulation_ph`, `raw_alkalinity_mg_l_caco3`, `coagulant_dose_actual_mg_l`

**Target families:** `coagulant_target_mg_l`

**Prerequisites:** Good quality and flow proof; Coagulation pH and alkalinity support the chosen adjustment.

**Timing helper, default tuning:** earliest review 5 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Inspect raw turbidity, alum dose, alkalinity and coagulation pH before adjusting.
2. High effluent turbidity is not permission to raise alum: excess alum can consume alkalinity and worsen removal.
3. Compare downstream response after a bounded change; if pH is already low or quality worsens, hold and request operator review.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### water.finished_ph — Finished pH

**Source:** [services/plant_sim/app/simulator.py](../services/plant_sim/app/simulator.py)

**Measurements:** `finished_water_ph`, `finished_alkalinity_mg_l_caco3`, `coagulation_ph`

**Target families:** `finished_water_ph_target`

**Prerequisites:** No chemical feed permissive failure.

**Timing helper, default tuning:** earliest review 6 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Use a small pH target adjustment only with good downstream pH and alkalinity measurements.
2. The pH and alkalinity states use alpha 0.18 per minute; earliest review is 6 minutes.
3. Check chlorine effectiveness and CT after changing pH.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### water.storage — Storage

**Source:** [services/plant_sim/app/simulator.py](../services/plant_sim/app/simulator.py)

**Measurements:** `clearwell_level_pct`, `elevated_tank_level_pct`, `raw_flow_m3h`, `distribution_flow_m3h`

**Target families:** `clearwell_target_pct`, `elevated_tank_target_pct`, `intake_gate_target_pct`

**Prerequisites:** No overflow, dry-running trip or field-position conflict.

**Timing helper, default tuning:** earliest review 15 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Storage changes through net inflow minus outflow over time; opening a valve does not instantly raise level.
2. Inspect level slope, usable storage, inflow, delivered flow and valve feedback.
3. Observe at least 15 simulated minutes for storage adjustments, unless protection requires immediate operator intervention.
4. Valve travel is capped at 12 percentage points per minute. Confirm feedback before interpreting level response.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### water.pressure — Pressure

**Source:** [services/plant_sim/app/simulator.py](../services/plant_sim/app/simulator.py)

**Measurements:** `zone_1_pressure_m`, `zone_2_pressure_m`, `zone_3_pressure_m`, `clearwell_level_pct`

**Target families:** `pressure_target_m`, `zone_1_isolation_target_pct`, `zone_2_isolation_target_pct`, `zone_3_isolation_target_pct`, `filter_outlet_valve_target_pct`

**Prerequisites:** Good zone pressure sensors; No latched trip or field mismatch.

**Timing helper, default tuning:** earliest review 5 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Check all zones and storage before raising pressure or restricting flow.
2. Use equal service priority for equal physical needs. Never close the last supply path.
3. Hydraulics refresh every 5 simulated minutes; wait for that update before another pressure adjustment.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### grid.balance — Balance

**Source:** [services/infrastructure_sim/app/grid.py](../services/infrastructure_sim/app/grid.py)

**Measurements:** `frequency_hz`, `system_demand_mw`, `gas_generation_mw`, `hydro_generation_mw`, `battery_soc_pct`

**Target families:** `gas_dispatch_mw`, `hydro_dispatch_mw`, `battery_dispatch_mw`, `demand_response_mw`

**Prerequisites:** No critical frequency or protection alarm; Battery energy supports the requested direction.

**Timing helper, default tuning:** earliest review 5 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Compare measured frequency, demand, generation and reserve before dispatch.
2. Increase bounded dispatch for shortfall only when equipment is available; reduce excess output when appropriate.
3. Gas ramps at 35 MW/min, hydro at 45 MW/min and battery at 50 MW/min. Frequency responds on a separate dynamic path.
4. Wait at least 5 simulated minutes and check storage state before another change.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### grid.voltage — Voltage

**Source:** [services/infrastructure_sim/app/grid.py](../services/infrastructure_sim/app/grid.py)

**Measurements:** `bus_1_voltage_pu`, `bus_2_voltage_pu`, `bus_3_voltage_pu`, `bus_4_voltage_pu`, `bus_5_voltage_pu`, `reactive_margin_mvar`

**Target families:** `capacitor_support_mvar`, `transformer_tap_pct`

**Prerequisites:** Good voltage readings; No critical overload or islanding protection alarm.

**Timing helper, default tuning:** earliest review 5 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Review every bus and reactive margin before changing capacitor support or tap.
2. Do not solve one low-voltage reading by creating overvoltage elsewhere.
3. Wait at least 5 simulated minutes and inspect the whole network response; breakers remain outside AI authority.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### nuclear.secondary — Secondary

**Source:** [services/infrastructure_sim/app/nuclear.py](../services/infrastructure_sim/app/nuclear.py)

**Measurements:** `electric_output_mwe`, `primary_pressure_mpa`, `steam_generator_level_pct`, `condenser_pressure_kpa_abs`

**Target families:** `turbine_load_target_mwe`, `condenser_cooling_pct`

**Prerequisites:** No critical alarm or reactor trip; Steam-generator levels support secondary operation.

**Timing helper, default tuning:** earliest review 5 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Only bounded secondary-side targets are available. Reactor protection and primary controls remain independent.
2. Check steam-generator inventories, condenser conditions and generator output before adjusting load or cooling.
3. Load output has alpha 0.22; condenser pressure alpha 0.20 times the configured response factor. Wait the server-supplied observation window.
4. Escalate critical conditions; never compensate for a protection trip with an AI target.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

### nuclear.heat_dispatch — Heat Dispatch

**Source:** [services/infrastructure_sim/app/nuclear.py](../services/infrastructure_sim/app/nuclear.py)

**Measurements:** `thermal_dispatch_mwth`, `primary_pressure_mpa`, `steam_generator_level_pct`

**Target families:** `thermal_dispatch_target_mwth`

**Prerequisites:** No primary or secondary protection condition.

**Timing helper, default tuning:** earliest review 6 simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.

1. Inspect heat-dispatch demand and secondary steam availability.
2. Change only the bounded thermal dispatch target. The heat loop has alpha 0.16 times its response setting.
3. Wait the server-supplied review interval; do not repeatedly increase dispatch before heat output responds.

**Escalate:** Required measurements are missing or unreliable. Independent protection is active, a prerequisite fails, or the observed response worsens.

## Context, memory and post-training

- **Contextualization:** retrieve domain-relevant SOPs and combine them with fresh readings, gate constraints and previous actions. This changes model inputs, not weights.
- **Critical-event memory:** preserve applied actions, rejections, overrides, missing signals and delayed outcomes with provenance. Summaries should retain unresolved hazards and point to original records.
- **Retrieval evaluation:** test procedure relevance on held-out scenarios, including conflicting alarms and missing sensors. A BERT-style reranker is an experiment, not an assumed improvement.
- **Qwen adaptation:** offline SFT/LoRA is a separate candidate experiment. Compare base and adapter on explicit actions, valid holds, gate violations, latency and delayed outcomes before promotion.
- **Jev:** use the same SOP and observation context with typed candidate choices. Supplying context does not fine-tune the hosted model.
- **Preference learning/RL:** retain failed and rejected trajectories. Gate acceptance alone is not a reward for successful control; use delayed outcomes and untouched evaluation scenarios. No automatic online weight updates are prescribed.

These are evaluation requirements and planned training directions, not claims that a trained adapter or reranker has passed validation.

## Maintaining this book

Edit `services/supervisor/app/plant_sops.json`, update its semantic version when meaning changes, and regenerate this document with:

```sh
.venv-interpret/bin/python scripts/build_sop_book.py
.venv-interpret/bin/python scripts/build_sop_book.py --check
```

Review sensor and target names against simulator contracts, source equations, prerequisites and cross-process effects. Keep actual limits in authoritative controller code rather than duplicating potentially stale numbers in prose. New real-world procedures require separate domain-expert validation.
