# Critical Infrastructure AI Control Lab

[Public recorded demo](https://ot-aigent-simulation.night-zone.com) · [Hosted simulator setup](docs/HOSTED_SIMULATOR.md) · [Reviewed lesson memory](docs/REVIEWED_MEMORY.md) · [MIT license](LICENSE)

This is an open-source research prototype. The public site currently replays recorded experiments; the full online simulation package is prepared separately and requires Cloudflare Workers Paid. Run the full simulation locally using the quick start below. Rule-based controls work without an available model; AI features need Ollama.

A local simulation and research environment for testing AI-assisted supervisory control in water, nuclear generation, and electric-grid systems.

The lab combines a treatment model, WNTR distribution hydraulics, a conceptual pressurized-water reactor model, a five-bus grid model, OPC UA, deterministic controllers, safety gates, Ollama, a historian, and three browser control rooms. It does not connect to real equipment.

WaterLab is currently a software-in-the-loop operator-training and control-research twin. It becomes an operational digital twin only after a reviewed physical asset model and read-only utility telemetry are synchronized and calibrated. See the [digital twin benchmark](docs/DIGITAL_TWIN_BENCHMARK.md) for a feature-by-feature comparison with EPA, Bentley, Autodesk, and Siemens approaches.

## Operator exercise upgrade

Open **Exercise console** for a common water, nuclear and grid workspace: pause,
resume, minute stepping, sensor trends, alarm acknowledgement, operator notes,
and CSV/JSON exercise exports. Water now checks combined storage mass balance;
grid accounts for disconnected islands and bounded battery energy; nuclear
records first-out trip causes and residual heat. See the
[operator exercise guide](docs/OPERATOR_EXERCISES.md) for runnable examples,
model assumptions and retention limits.

```sh
python3 scripts/run_exercise.py nuclear --scenario coolant_pump_trip --minutes 90
python3 scripts/run_exercise.py grid --scenario generator_trip --minutes 90
```

## What you can do

- Watch raw water move through alum coagulation, clarification, filtration, NaOH pH correction, chlorination, storage, and distribution
- Inspect live sensors, equipment state, alarms, pressure, demand, energy, and water-quality trends
- Run normal and fault scenarios with fixed random seeds
- Compare baseline, advisory, shadow, and safety-gated automatic control
- Test a deliberately unsafe AI proposal and confirm that the gate blocks it
- Export experiment samples as CSV or JSON
- Browse simulated OT tags through OPC UA inside the private Docker network
- Inspect seven named process checkpoints from raw-water intake to zone delivery
- Track raw, coagulation, and finished-water pH; alkalinity consumption and recovery; chemical feed runtime; clearwell T10; and calculated chlorine CT
- Follow a resettable elapsed run clock that stops on pause and advances at the selected simulation speed
- Open, close, and throttle simulated gates and isolation valves through bounded supervisory targets
- Compare valve command, travelled position, flow, upstream pressure, downstream pressure, and differential pressure
- Give the local model a bounded, auditable memory of similar decisions
- Compare synthetic OPC UA telemetry with model predictions through pressure RMSE, flow residual, fit status, and synchronization age
- Inspect PI loop setpoint, process value, output saturation, equipment runtime, restart inhibition, permissives, first-out trips, and the active backwash phase
- Inspect bulk and day tanks for alum, NaOH, and sodium hypochlorite, including transfer valves, metering pumps, calibration columns, non-return valves, and injection points
- Switch to a generic three-loop PWR control room with a reactor vessel, three primary loops, pressurizer, steam generators, turbine generator, condenser, feedwater, industrial heat dispatch, and independent protection
- Compare loop balance, rolling trends, alarm transitions, computerized response guidance, model health, equipment condition, and reduced-order tuning presets
- Switch to a five-bus power-grid control room with generators, renewable sources, battery storage, transmission lines, breakers, voltage, frequency, reactive support, and customer demand
- Run nuclear transients and grid disturbances while observing deterministic protection and AI authority boundaries

All operating thresholds are illustrative simulation values. They are not regulatory limits and must not be used for a real plant.

## Quick start on Apple Silicon

Requirements:

- Docker Desktop
- Ollama for macOS
- About 8 GB of free disk space for images and the default model

Install Ollama from [ollama.com/download](https://ollama.com/download), then run:

```sh
ollama pull qwen3:8b
ollama serve
```

In a second terminal:

```sh
cp .env.example .env
docker compose up --build
```

Open [http://localhost:18780](http://localhost:18780). The landing page is a five-chapter **Guided walkthrough**, with presentation view, speaker notes, baseline capture, predefined disturbance, local-agent evaluation and evidence review. See the [ten-minute audience script](docs/AUDIENCE_WALKTHROUGH.md).

The dashboard is bound to `127.0.0.1`. PostgreSQL and OPC UA are not published to the host.

Use the top navigation to switch among Water overview, Water HMI, Nuclear PWR, Power grid, Experiments, Exercise console, and Local AI agents. Each control room has its own simulated clock, scenario selector, speed, alarms, manual controls, and AI supervisor panel.

See [the equipment and local-agent guide](docs/LOCAL_AI_OPERATOR_GUIDE.md) for the new asset controls, severe-incident exercises, decision inspector and paired research studies.

## Local worker and reviewer agents

Use `python3 scripts/local_agents.py run --worker grid --reviewer safety --reviewer consistency` to generate a non-actuating local proposal and have two reviewer roles inspect its emitted reasoning and decision evidence. Five named profiles, configurable context windows, exact-quote checks and JSON/Markdown exports are described in [the local agent team guide](docs/LOCAL_AGENT_TEAM.md).

## Three AI control boundaries

The water model lets AI propose pressure, storage, pH, chlorine, and bounded valve targets. The nuclear model is intentionally stricter. AI may propose turbine load, condenser cooling, and bounded industrial heat dispatch only. It has no route to control rods, reactor trip, engineered safety features, main steam isolation, or emergency feedwater. The grid model lets AI propose generation dispatch, battery power, demand response, transformer tap, and reactive support. Protection relays and transmission breakers remain deterministic or operator-confirmed.

For nuclear and grid decisions, the supervisor sends a compact live snapshot and the last audited decision to Ollama. Ollama returns strict JSON. The domain simulator validates the keys, ranges, maximum change, confidence, current alarms, and control mode. A valid gated-auto decision receives a five-simulated-minute lease. A reset, stale snapshot or control-mode change rejects an in-flight proposal. Mode changes and lease expiry release AI targets. If Ollama is unavailable or invalid, the failure is recorded and deterministic process control continues; nuclear/grid do not silently substitute a policy for the local model.

The nuclear and grid models are educational reduced-order simulations. They are useful for showing inputs, outputs, time progression, fault consequences, AI proposals, and safety rejection. They are not licensed engineering, dispatch, protection, or operator-training tools. See [the nuclear and grid model notes](docs/NUCLEAR_AND_GRID_MODELS.md).

Apollo Watcher can be added as an out-of-band behavioural monitor, but it must not receive actuator authority or become part of deterministic protection. See the [Watcher security architecture](docs/WATCHER_SECURITY_ARCHITECTURE.md) for the proposed trust zones, one-way event relay, credential boundaries, privacy limits, and validation plan.

The optional Watcher relay exports only allowlisted Ollama decision records. It excludes Codex sessions, chat transcripts, source files, raw prompts, sensor dumps, manual actions, and deterministic fallbacks. It is disabled and set to dry-run by default.

## First demonstration

1. Open **Experiments**.
2. Select **Normal 24-hour cycle**, seed `42`, speed `60x`, and **Baseline**.
3. Start the run and inspect the overview and industrial HMI.
4. Reset the run, select **Shadow**, and start it again.
5. Compare the AI proposal with baseline control. Shadow mode never applies the proposal.
6. Create a **Gated auto** run with **Unsafe AI proposal**.
7. The decision panel should show a rejected proposal, and no unsafe setpoint should reach an actuator.

At `60x`, a 24-hour simulation takes about 24 minutes of wall-clock time. The default `10x` speed makes process changes easier to watch.

## Control modes

| Mode | AI proposal | Safety gate | Applied |
| --- | --- | --- | --- |
| Baseline | No | Deterministic controller only | Baseline commands |
| Advisory | Yes | Evaluated and logged | No |
| Shadow | Yes | Evaluated and compared | No |
| Gated auto | Yes | Must pass every rule | One five-minute interval |

The PLC service is the only service that writes OPC UA actuator nodes. Ollama can suggest bounded setpoint changes, but it cannot write pump, valve, or dose outputs.

## PLC-style control hierarchy

The baseline controller is stateful. Five PI blocks regulate clearwell level, distribution pressure, elevated storage, chlorine residual, and finished-water pH. Each block has integral anti-windup and an output slew limit. A two-minute start timer and an eight-minute stop timer stage the booster pump. Runtime records enforce minimum pump off-times and count restarts.

Permissives sit above the control loops. They check the open flow path, conservative tank-level selectors, distribution availability, sensor quality, treatment flow proof, chemical inventory, emergency state, and latched trips. A failed permissive inhibits the affected equipment or chemical feed. A trip records the first hazardous event and remains latched until the process is healthy and an operator requests reset.

Filter backwash is a feedback-driven sequence, not a direct actuator bit. It isolates the filter outlet, confirms valve travel, backwashes for five simulated minutes, rinses for two simulated minutes, then reopens the outlet and confirms return to service. The sequence needs adequate clearwell storage, elevated filter differential pressure, and good telemetry. It aborts and returns the filter toward service if clearwell storage drops below the abort point or required telemetry is lost. All times and limits are illustrative simulation settings.

## How AI reaches the digital twin

```text
Plant snapshot + selected decision memory
                |
                v
       Ollama structured proposal
                |
                v
 Deterministic PLC safety gate and prediction
                |
         accepted setpoint lease
                |
                v
 Baseline controller maps targets to rate-limited commands
                |
                v
       OPC UA actuator nodes and digital twin
```

The model proposes supervisory targets such as pressure, chlorine residual, finished-water pH, storage level, or one valve target. It never receives an unrestricted tool and it cannot address an OPC UA node. The pH target is converted into a bounded NaOH dose by the PLC from raw pH, alkalinity, and alum dose. Invalid JSON, a timeout, stale data, low confidence, a conflicting chemical change, a conflicting valve action, or a failed safety prediction leaves the baseline controller in charge.

The local model's memory is explicit application memory. PostgreSQL keeps decisions and plant samples. Before each AI call, the supervisor retrieves up to eight same-scenario episodes with the closest numeric plant conditions and includes them in the prompt. The model itself does not remember earlier calls just because Ollama remains loaded. The endpoint `GET /api/v1/memory` shows the exact episodes used in the latest prompt.

## Valves and process checkpoints

The twin includes an intake gate, filter outlet isolation valve, a pressure-reducing valve, and one isolation valve for each demand zone. A command and field position are separate values. Position changes by at most 12 percentage points per simulated minute, so the HMI shows opening, closing, throttled, open, closed, and interlocked states. Flow capacity follows opening, and a quadratic loss relationship converts throttling into differential pressure. WNTR pressure-dependent demand, a PRV, and zone TCVs provide the hydraulic calculation, with a deterministic analytical fallback.

Seven checkpoints cover intake, clarifier outlet, combined filter effluent, post-filter chemical conditioning, clearwell, pump discharge, and zone delivery. Each checkpoint has a purpose, sensor tags, data quality, and operating status. These are simulation checkpoints, not a regulatory monitoring plan.

## Treatment chemistry and chlorine contact

The chemistry path is linked, not a set of independent gauges:

```text
Raw pH and alkalinity
    -> alum alkalinity demand
    -> coagulation pH and turbidity removal
    -> clarification and filtration
    -> post-filter NaOH pH correction
    -> chlorine dose
    -> baffled clearwell contact time and CT
    -> high-lift pumping and distribution
```

The carbonate calculation infers dissolved inorganic carbon from raw pH and alkalinity, subtracts an illustrative alum alkalinity demand, adds the stoichiometric alkalinity from pure NaOH, and solves the carbonate balance for pH. Each dose target is converted from mg/L into a flow-paced metering-pump rate in L/h using the current water flow and an assumed product strength. The chlorine model calculates T10 from usable clearwell volume, current flow, and a 0.30 baffling factor, then reports `CT = residual x T10`. Temperature and source-water demand affect chlorine decay. The HMI also shows free-chlorine HOCl fraction and feed-pump runtime.

## Interactive hazard exercises

The Industrial HMI contains six press-to-run exercises for demonstrations:

- Clearwell overflow caused by forced intake and restricted discharge
- A false low clearwell-level signal
- A false high chlorine-residual signal
- An intake pump held on against a forced-closed filter outlet valve
- A forced-closed Zone 2 isolation valve
- A forced chlorine overfeed

Each exercise changes simulated field behavior while leaving the PLC command visible. This makes command-versus-position, command-versus-dose, and reported-versus-modeled disagreements easy to inspect. The independent process model raises integrity flags, the alarm system records the event, the PLC issues its protective command, and the AI safety gate rejects optimization while the plant is critical. The red emergency button still has priority over every injected override.

These controls are local simulation features. They do not include drivers, credentials, addressing, or command paths for real equipment.

These relationships are suitable for control research and fault demonstrations, but they are not a plant design or compliance calculation. A real application needs site chemistry, coagulant formulation, chemical strength, mixing tests, tracer testing, required CT tables, and state approval.

## Python notebook

The notebook at `notebooks/waterlab_control.ipynb` is a safe client for the supervisor API. It does not import an OPC UA client and cannot write raw actuators.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r notebooks/requirements.txt
jupyter lab notebooks/waterlab_control.ipynb
```

Leave `RUN_DEMO = False` for read-only inspection. Set it to true to create a simulated run, step it, and submit a confirmed setpoint request through the gate.

## Services

```text
Browser :18780
    |
  Nginx web ------ app_net ------ Supervisor API ------ PostgreSQL
                                      |
                                  internal bridge
                                      |
                ot_net -------- PLC controller -------- Water simulator
                    |              writes OPC UA          owns OPC UA
                    |
                    +-------- Nuclear and grid simulators

Native Ollama :11434 <---------- Supervisor API through host.docker.internal
```

`ot_net` is an internal Docker network. Only the supervisor joins both networks.

## Commands

```sh
make up          # Build and start the lab
make down        # Stop the lab
make logs        # Follow service logs
make build       # Build all images
make test        # Run unit tests in a container
make pull-model  # Pull the configured native Ollama model
```

For Linux or a CPU-only demonstration, the optional container profile is available:

```sh
docker compose --profile ollama-container up --build
```

Change `OLLAMA_BASE_URL` to `http://ollama:11434` in `.env` when using that profile. Pull the model inside the container before starting an AI run:

```sh
docker compose --profile ollama-container exec ollama ollama pull qwen3:8b
```

## API

The Nginx service proxies the API under `http://localhost:18780/api/v1`.

- `GET /state`
- `GET /scenarios`
- `GET /injections`
- `POST /injections/{injection_id}`
- `DELETE /injections`
- `GET /runs`
- `POST /runs`
- `POST /runs/{id}/start`
- `POST /runs/{id}/pause`
- `POST /runs/{id}/reset`
- `POST /runs/{id}/step`
- `PUT /control/mode`
- `POST /control/manual`
- `POST /emergency-stop`
- `GET /decisions`
- `GET /memory`
- `GET /alarms`
- `GET /runs/{id}/metrics`
- `GET /runs/{id}/export?format=csv`
- `GET /runs/{id}/export?format=json`
- `WS /live`
- `GET /infrastructure/state`
- `GET /infrastructure/scenarios`
- `POST /infrastructure/{domain}/command`
- `POST /infrastructure/{domain}/manual`
- `POST /infrastructure/{domain}/ai`
- `PUT /infrastructure/nuclear/tuning`

Interactive API documentation is available inside the Docker network from the supervisor's `/docs` route. It is intentionally not linked from the control room.

## Project structure

```text
shared/                    Validated contracts, limits, and OPC UA tag names
services/plant_sim/        Treatment model, WNTR hydraulics, scenarios, OPC UA server
services/infrastructure_sim/ Conceptual nuclear and five-bus grid models
services/plc_control/      Baseline controller, safety gate, OPC UA writer
services/supervisor/       Run manager, Ollama client, historian, REST and WebSocket API
services/web/              React control room and Nginx reverse proxy
tests/                     Unit and opt-in integration tests
notebooks/                 Safe API control walkthrough
docs/                      Architecture, safety, and experiment notes
```

## Safety boundary

This release is for local simulation only. It has no code path for connecting to a real PLC. Do not reuse its illustrative limits, simplified chemistry, controller gains, or hydraulic assumptions in an operating facility. See [docs/SAFETY.md](docs/SAFETY.md).

The official EPA, WNTR, OPC Foundation, and Ollama sources used for this upgrade are listed in [docs/REFERENCES.md](docs/REFERENCES.md).

### Run a gradual recovery experiment

`python3 scripts/run_recovery_timeline.py` compares baseline water control with a real local LLM responding to a sustained quality disturbance. It saves a plotted timeline, per-exchange context and gate evidence, and pauses after independently confirmed recovery or the experiment limit. See [the recovery timeline protocol](docs/RECOVERY_TIMELINE.md).

### Inspect evidence, risk and model internals

The new **Evidence & risk** workspace links saved sensor timelines, local-model exchanges, gate results and measured process outcomes. Its separate instrumented Qwen3 4B experiment uses **Transformers, PyTorch and NNsight** to capture activations and test 48 activation replacements. Open `/research.html` on the web server, or the matching control-room tab. See [the dashboard walkthrough and reproducible experiment guide](docs/MECHANISTIC_INTERPRETABILITY.md).

### Present the saved research demo

Double-click **Start Research Demo.command** to open the built, read-only walkthrough at `http://127.0.0.1:18774/research.html`. Choose **Presentation view** for five guided chapters, recorded playback, speaker notes, interactive saved activation swaps and an evidence brief. Python 3 is sufficient at presentation time; Docker and Ollama are not required. Rebuild after source or artifact updates with `npm run build --prefix services/web`.

### Local ports

WaterLab uses a separate host port range: **18780** for the live lab, **18774** for the recorded demo, and **18773** for Vite development. Internal Docker ports and the shared Ollama endpoint on **11434** are unchanged. The demo launcher uses 18774 automatically; development fails clearly if 18773 is occupied.
