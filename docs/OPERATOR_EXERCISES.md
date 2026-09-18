# Operator exercises

Start the local stack with `docker compose up -d --build`, then open
http://localhost:18780 and select **Exercise console**. Choose Water treatment,
Nuclear PWR, or Power grid. Each domain has an independent process and clock.
Use **Open HMI** for equipment controls and AI settings.

1. Select a scenario. This resets that domain's process and exercise record.
2. Step one minute at a time, or start continuous operation. Nuclear/grid also
   support ten-minute steps; every intervening minute is recorded.
3. Select a sensor to inspect its trend. Review model and measured signals together.
4. Acknowledge an alarm and enter your observation. Acknowledgement records
   recognition; it does not clear the condition or reset protection. If the same
   condition clears and recurs, it needs a new acknowledgement.
5. Download CSV for analysis or JSON for sensors, quality, commands, AI decision
   events, operator notes, alarm transitions, and cumulative metrics.

Speed and AI mode changes in the nuclear/grid HMI preserve elapsed time.
Changing scenario and pressing Reset begin a new record. Water pause/resume
preserves elapsed time. Water manual stepping synchronizes the OPC UA state and
performs a deterministic PLC scan between simulated minutes.

## Suggested exercises

| Domain | Exercise | Observe |
|---|---|---|
| Water | Normal day, then a Zone 2 isolation injection from Water HMI | Valve command versus position, served demand, pressure, storage balance and PLC permissives |
| Water | Clearwell overflow injection | Storage response, overflow volume and protective commands |
| Nuclear | Reactor coolant pump trip; step past minute 20 | Loop B flow, first-out trip cause, reactor power and residual heat |
| Nuclear | Loss of feedwater | Individual steam-generator inventories and independent protection |
| Grid | Generator trip; step past minute 30 | Ramping, battery SOC, unserved load and cumulative unserved energy |
| Grid | Open both L-CM and L-SM together through the manual API in a healthy initial state | Isolated Metro bus, zero served demand on that bus, continuing flow elsewhere |

The grid's existing operator gate blocks breaker operations while critical.
Reset an islanding exercise to restore its initial topology. This release does
not implement synchronism checks or a restoration switching procedure.

## Command-line runs

These commands use the local supervisor API and require only Python 3. They
save the preceding domain record before starting a fresh run, save JSON and CSV
under `artifacts/exercises`, and leave the process paused.

```sh
python3 scripts/run_exercise.py water --scenario normal_day --minutes 60 --seed 42
python3 scripts/run_exercise.py nuclear --scenario coolant_pump_trip --minutes 90
python3 scripts/run_exercise.py grid --scenario generator_trip --minutes 90
```

Use `--mode baseline`, `advisory`, `shadow`, or `gated_auto`. Water has seeded
noise; the current nuclear/grid dynamics are deterministic. Nuclear/grid automatic decisions request the local model at most once per
five simulated minutes while running outside baseline mode. The HMI's
**Run AI supervisor** button also requests Ollama. Local-model errors retain
deterministic control and are recorded. Record the model, tuning and interventions when comparing results.
Ollama outputs are not guaranteed reproducible.

## Modeling changes and limits

- Water accounts for clearwell and elevated storage after delivered demand is
  determined. Pump withdrawal cannot exceed available clearwell water. The
  illustrative elevated-tank path can supply up to 25 m³/h above 20% storage or
  accept up to 20 m³/h of pump surplus. The `water_balance_error_m3` tag checks
  combined storage change against treatment inflow, delivered flow and overflow.
  This is a conservation check within the model, not calibration evidence.
- Grid DC flow solves connected components separately, with a reference angle
  per component. A bounded ±120 MW interchange exists only at B1. Short supply
  reduces served customer load proportionally within each island; excess supply
  is reported as curtailment. An island with no power has zero voltage. Battery
  usable SOC is 10–95%, with 400 MWh capacity and 95% one-way efficiency.
  Bus voltage remains a heuristic and frequency an aggregate minute-resolution
  response. The model does not resolve island frequency, AC reactive-power flow,
  electromechanical transients, relay timing, or synchronism.
- Nuclear protection latches the initiating conditions and simulated minute.
  Causes detected together are retained together. The residual-heat indicator
  exposes the existing illustrative exponential decay floor; it is not a
  standards-based decay-heat calculation. These are generic three-loop PWR
  dynamics, not a plant-specific nuclear simulator.

The exercise recorder retains the latest 1,441 samples (initial state plus one
day of minute samples) and 2,000 events **in memory**. It exposes dropped counts;
cumulative metrics cover the entire exercise. Export before reset or service
restart. Water's existing PostgreSQL historian is a separate persistent record.
CSV contains numeric sensor samples; JSON also contains command and event data.
Integrals use end-of-minute values, and critical duration uses end-of-minute
alarm state. Sub-minute excursions cannot be measured by these models.

## References

The engineering relationships are informed by public primary references; all
new numerical limits above are local illustrative assumptions.

- [EPA EPANET](https://www.epa.gov/water-research/epanet): extended-period network
  hydraulics and water quality, including storage, pressures and chemical transport.
- [EPA WNTR manual](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P1010W6J.TXT):
  pressure-dependent demand for service shortfalls.
- [NRC PWR overview](https://www.nrc.gov/reactors/power/pwrs): primary coolant,
  steam generator and secondary-cycle separation.
- [NRC Reactor Concepts Manual](https://www.nrc.gov/sites/default/files/doc_library/cdn/legacy/reading-rm/basic-ref/students/for-educators/04.pdf):
  public descriptions of PWR systems.
- [MATPOWER manual](https://www.matpower.org/docs/manual.pdf) and
  [island identification](https://matpower.org/docs/ref/matpower6.0/find_islands.html):
  power balance, reference buses and disconnected network components.

Run `make test` to execute the offline regression suite in a container with the
water model and WNTR dependencies installed. The opt-in live integration tests
remain separate from this offline suite.
