# Simulation safety model

This document describes controls for a research simulator. It is not a safety case for a real water system.

## Authority boundary

Ollama receives a compact plant snapshot and returns a schema-constrained proposal. The schema contains only supervisory setpoints and a backwash request. Raw pump speed, valve position, and dose outputs are absent from the AI schema.

The PLC service owns the safety gate and actuator writer. This separation means a compromised or unreliable model response still cannot bypass the deterministic checks through the documented application path.

The interactive hazard injector changes behavior inside the plant simulator. It does not write OPC UA commands and has no connection path to real equipment. Commanded and physical values remain separate so the dashboard can show a failed or compromised field response.

An active injection places the simulated plant in a critical state and blocks AI optimization. Independent model checks compare reported level and chlorine values with process estimates. Command-feedback checks identify forced valve and chemical-feed behavior. The emergency stop has priority over every injected override.

## Gate checks

The gate rejects a proposal when:

- Confidence is below `0.55`
- A sensor required for the proposed target is missing, stale, uncertain, or bad quality
- The emergency stop is active
- The plant is already in a critical state
- A target falls outside its illustrative permitted range
- A target cannot be brought inside its absolute range
- A controller trip is latched
- A valve command and field position disagree during a related proposal
- A backwash request lacks adequate clearwell storage
- A lower chlorine target conflicts with elevated filtered turbidity
- A higher finished-water pH target conflicts with low calculated chlorine CT
- A higher pH target conflicts with a lower chlorine target
- A high pressure target conflicts with low elevated-tank storage
- Ollama times out, is unavailable, or returns an invalid schema

Rejected proposals retain baseline control. The proposal, failed rules, and fallback reason are stored in the historian.

A proposal that is inside the absolute range but exceeds the permitted movement is reduced to the largest allowed step and labelled `modified`. The gate also projects clearwell level, minimum zone pressure, chlorine residual, and finished-water pH across a conservative 15-minute horizon. Crossing a configured boundary rejects the proposal.

The filter backwash request passes through a separate PLC sequence. Starting requires a clearwell level of at least 50 percent, filter differential pressure of at least 38 kPa, and good sequence telemetry. During the sequence, a clearwell level below 35 percent or lost telemetry triggers an abort and controlled return. These thresholds are demonstration values.

Chemical metering has a common treatment-flow permissive and separate inventory checks. Loss of flow proof stops alum, NaOH, and hypochlorite delivery even if a dose command remains present. This preserves the distinction between commanded dose and confirmed delivery.

## Emergency stop

The fixed red control in the browser calls the PLC service directly through the supervisor. The PLC writes zero-speed and zero-dose commands and sets the emergency-stop tag. The control mode returns to baseline. This is a software demonstration of an emergency stop, not a substitute for a hardwired safety circuit.

## Illustrative limits

The code stores its demonstration thresholds in `shared/limits.py`. These values support repeatable software experiments only. They do not represent regulatory limits, operating guidance, or an engineering design.

## Out of scope

- Real PLC, SCADA, pump, valve, analyzer, or plant integration
- Authentication and role-based operator authorization
- Safety integrity level assessment
- Regulatory compliance
- Calibrated site-specific water chemistry and regulatory CT compliance
- Real exploit tooling, credential attacks, malware, command replay, network spoofing, and prompt poisoning
- Public internet deployment

## Nuclear and grid boundary

The nuclear and grid rooms are conceptual demonstrations, not operational twins. Nuclear AI is separated from reactor protection, control rods, boron control, engineered safety features, primary pumps, main steam isolation, and emergency feedwater. Its only nuclear-domain targets are turbine load, condenser cooling, and bounded industrial heat dispatch. Heat dispatch is rejected during a reactor trip, any critical process state, or a low steam-generator inventory. Grid AI is separated from protection relays and automatic transmission-breaker action. The UI does not contain addresses, protocols, settings, credentials, or drivers for real nuclear or grid equipment.

The public INL capability descriptions informed the display and research workflow, but the project does not include licensed RELAP5-3D software or plant-specific models. Reduced-order tuning presets are clearly labelled as illustrative response gains, not engineering coefficients or protection settings.

The local model sees a compact simulation snapshot, the permitted fields, illustrative bounds, and one prior audited decision. It returns structured JSON with no tool access. The simulator runs its own gate after Pydantic validation. The gate, not the model, decides if any proposal is usable.
