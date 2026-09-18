# Architecture

## Process model

The treatment loop advances once per simulated minute. It tracks raw flow, turbidity, pH, alkalinity, alum dose, coagulation pH, clarification, filtration, post-filter NaOH correction, chlorine dose, clearwell storage, contact time, and chlorine decay.

The chemistry calculation uses a carbonate equilibrium with conserved dissolved inorganic carbon. Alum consumes an illustrative 0.50 mg/L of alkalinity as CaCO3 for each 1 mg/L dose. Pure NaOH adds 1.25 mg/L of alkalinity as CaCO3 for each 1 mg/L dose, based on equivalent weight. A bisection solver converts the resulting alkalinity back to pH. The dynamic finished-water state approaches the equilibrium result over time so a feed change is not instantaneous.

NaOH is injected after filtration in this model. This keeps it separate from the alum application point and lets the simulator distinguish coagulation pH from finished-water corrosion-control pH. The baseline PLC computes NaOH feedforward from raw pH, raw alkalinity, alum dose, and the finished-water pH target, then adds bounded pH feedback.

The plant converts the commanded treatment doses into solution flow for the metering pumps. The initial assumptions are 640 g/L alum product, 320 g/L NaOH in a 25 percent solution, and 125 g/L available chlorine in sodium hypochlorite. These values are simulation inputs, not purchasing specifications. The OPC UA model exposes solution flow in L/h, delivered NaOH dose, and cumulative feed runtime.

Clearwell T10 is estimated from active volume divided by current flow, multiplied by a 0.30 illustrative baffling factor. Calculated CT is the outlet chlorine residual multiplied by T10. The model also reports water temperature and the pH-dependent hypochlorous-acid fraction. Required CT is not calculated because that requires a defined organism, log-inactivation target, approved tables, and validated plant conditions.

The distribution loop advances every five simulated minutes. It uses WNTR pressure-dependent demand to represent the clearwell source, high-lift pump, pressure-reducing valve, three zone junctions, zone throttle-control valves, elevated storage, and connecting pipes. If a WNTR solve fails, the simulator records that it used the analytical valve fallback and continues the run. This keeps the control lab observable during a hydraulic solver problem.

A valve command and travelled field position are separate. Position changes by at most 12 percentage points per simulated minute. Partial closure reduces flow capacity and adds quadratic head loss. OPC UA publishes the command, actual position, flow, upstream pressure, downstream pressure, differential pressure, and state.

Operational checkpoints cover the raw-water intake, clarifier outlet, combined filter effluent, post-filter chemical gallery, clearwell, high-lift pump discharge, and demand-zone boundaries. Each checkpoint carries its purpose, sensor tags, data quality, and status.

Time-varying demand comes from a deterministic daily pattern plus seeded noise. Scenario modifiers add turbidity, leaks, pump degradation, or sensor faults at fixed simulated times.

## Control path

The plant simulator owns sensor and actuator state. The PLC controller reads the plant once for each new simulated minute and calculates baseline actuator commands. It is the only client that writes actuator nodes.

The PLC calculation has four layers:

1. Sensor selection compares reported clearwell level with the independent model estimate. The high selector protects against overflow and the low selector protects pump suction.
2. PI blocks calculate normal pump and chemical commands with anti-windup, integral hold on poor data, feedforward terms, and output slew limits.
3. Equipment permissives, delayed starts and stops, minimum off-times, emergency overrides, and first-out trip latches determine which commands may run.
4. The filter backwash sequencer owns the isolation, backwash, rinse, and return phases. It advances from valve feedback and simulated time, not from a single model response.

Every AI decision follows this path:

```text
Plant snapshot and selected decision memory
    -> compact supervisory prompt
    -> Ollama structured response
    -> Pydantic validation
    -> deterministic safety gate in PLC service
    -> mode check
    -> temporary setpoint change or baseline fallback
```

The AI decision interval defaults to five simulated minutes. A gated proposal changes controller setpoints only. The baseline controller still calculates every raw actuator output.

The safety gate evaluates only the sensor dependencies for the targets in a proposal. It also checks confidence, finite values, freshness, absolute limits, rate limits, active PLC trips, process conflicts, valve command-feedback agreement, and a conservative 15-minute projection of storage, pressure, chlorine, and pH. An accepted proposal receives a lease for one AI decision interval. It cannot remain in force silently.

## Interactive hazard injection

The HMI calls the supervisor injection API. The supervisor proxies the request to the isolated plant simulator. The injector changes simulated field behavior, not PLC commands, so a presenter can compare the requested output with the actual pump, valve, sensor, or chemical-feed response. Every active injection sets the plant critical state, adds an auditable process alarm, and prevents gated AI optimization.

Sensor-spoof exercises keep protocol quality marked good to represent a syntactically valid but false reading. A separate process-model estimate provides the independent comparison. Forced valve and dosing exercises retain the PLC command alongside field position or delivered dose. The emergency-stop state is evaluated before injected overrides and remains the highest-priority response.

## Local model memory

Ollama context is rebuilt for every decision. The supervisor selects a bounded number of same-scenario decisions with similar turbidity, storage, chlorine, header pressure, and leakage values. It sends the prior sensor summary, proposal, and gate outcome with the current snapshot. The retrieved episodes remain audited in PostgreSQL and are visible through the memory API.

Keeping the model loaded improves response time but does not preserve plant history. Hidden reasoning is never stored. Retrieved memory is advisory context and cannot override a safety rule.

## Persistence

PostgreSQL stores:

- Run configuration and state
- Plant snapshots
- AI proposals and gate decisions
- Alarm observations
- Calculated run metrics

The active run manager samples once per new simulated minute. Resetting a run clears its samples, decisions, alarms, and metrics, then restores the original seed and configuration.

The plant owns an integer elapsed-minute counter. It advances only when the simulation loop advances, stops while paused, and resets to zero with the run. At 1x, 10x, and 60x, one simulated minute takes 60, 6, and 1 wall-clock seconds. The web clock reads this plant counter, so it cannot drift ahead of the digital twin.

## Network isolation

The plant and PLC are only on `ot_net`, which Docker marks as internal. The web app and database are only on `app_net`. The supervisor is the bridge because it needs read access to simulated OT state and write access to application data.

Nginx is the only published service. Its host binding is `127.0.0.1:18780`. The browser cannot address PostgreSQL or OPC UA directly.

## Nuclear and grid models

The `infrastructure-sim` service owns two separate time-progressive reduced-order models. It is on the internal OT network and exposes no host port. The supervisor proxies control-room commands and is the only component that calls Ollama.

The generic PWR model advances one simulated minute at a time. It links reactor thermal power, three primary-loop flows and temperatures, primary pressure, pressurizer response, three steam-generator inventories, steam and feedwater flow, hotwell and deaerator inventory, condenser backpressure, circulating-water heat rejection, turbine speed, electric output, and bounded industrial heat dispatch. Independent deterministic logic handles reactor trip, control-rod insertion, main steam reduction, and auxiliary feedwater. The AI proposal schema contains only turbine load target, condenser cooling, and industrial heat dispatch.

Nuclear snapshots also include rolling history, computerized response guidance, condition estimates, model-balance indicators, alarm transitions, and the active reduced-order tuning profile. These are read-only context for the local model. They do not expand its command authority.

The grid model advances generation, load, renewable availability, battery state of charge, frequency, bus voltage, and line loading each minute. A five-bus DC power-flow calculation resolves six line flows and breaker topology. Reduced-order frequency dynamics respond to the generation-demand imbalance. The AI proposal schema contains dispatch, battery, demand response, transformer tap, and reactive support. Breakers and protection are outside the AI schema.

Both domain services accept an externally generated structured proposal. They independently validate the proposal and apply it only in gated-auto mode. Advisory and shadow modes never apply the change. Confidence below 0.55, unauthorized keys, excessive movement, an out-of-range target, or a critical process state causes rejection.
