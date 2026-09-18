# Nuclear and grid simulation notes

## Purpose and fidelity

These two simulators show the operating relationships a visitor expects to see in a control room. They are time-progressive, internally linked, scenario-driven, and safety-gated. They are not high-fidelity engineering tools. The values are illustrative and the models must not be used for plant operation, protection settings, dispatch, licensing, or training credit.

## Public INL capability pattern

The nuclear room uses only public capability descriptions from Idaho National Laboratory. INL's Human System Simulation Laboratory describes configurable control rooms, digital and analog displays, advanced alarms, automated controls, predictive maintenance, operational visualization, computerized procedures, and human-operator evaluation under normal and emergency conditions. Public INL flexible-plant research also describes coupled thermal and electrical dispatch to an industrial process.

This lab implements those concepts as a generic research demonstration. It does not copy a plant control room, use plant-specific settings, or reproduce INL software. RELAP5-3D is an export-reviewed, licensed code. This project does not contain it and makes no claim of equivalent fidelity.

## Generic three-loop PWR model

The process mimic follows the US NRC pressurized-water reactor arrangement:

```text
                         +-> Loop A steam generator and RCP -+
Reactor vessel and core +-> Loop B steam generator and RCP -+-> steam header
                         +-> Loop C steam generator and RCP -+
                                                               |
                                      +------------------------+-----------------+
                                      |                                          |
                                      v                                          v
                              turbine and generator                 industrial heat exchanger
                                      |
                                      v
                                  condenser
                                      |
                    condensate pump -> deaerator -> feed pump
                                      |
                                      +-> three steam generators
```

Inputs include control-rod position, boron concentration, pressurizer heaters and spray, main feedwater valve, auxiliary feedwater, main steam valve, turbine load target, condenser cooling, and industrial heat target. Outputs include reactor power, thermal power, primary temperature and pressure, pressurizer level, three loop flows and temperatures, three steam-generator levels, steam and feedwater flow, hotwell and deaerator levels, condenser pressure, circulating-water temperatures, turbine speed, electrical output, thermal dispatch, containment pressure, and a radiation monitor.

Included scenarios are normal operation, turbine load rejection, loss of feedwater, a Loop B coolant-pump trip, condenser vacuum loss, pressurizer sensor bias, Loop B feedwater restriction, industrial heat ramp, industrial heat-load rejection, and feedwater-pump degradation. The trip logic uses illustrative thresholds and remains fully independent from the AI path.

The room also exposes six rolling trends, alarm state transitions, four computerized response-guidance cards, steam and feedwater balance checks, loop-level spread, trip margin, condenser fouling, feedwater-pump efficiency, and RCP bearing health. Four tuning presets alter reduced-order response speeds. These presets support demonstrations and sensitivity exercises. They are not physical plant coefficients.

The IAEA reports that current AI applications at operating nuclear plants are independent of safety-related systems and functions. This simulator follows that boundary. AI can optimize three non-safety supervisory targets: turbine loading, condenser cooling, and industrial heat dispatch. It cannot manipulate the reactor, main steam isolation, feedwater safety response, or protection system.

Each AI proposal is a one-interval request. The deterministic gate checks the allowed keys, range, maximum change, confidence, active critical alarms, reactor trip state, and minimum steam-generator level. The independent baseline controller remains responsible for primary pressure, inventory, protection, and emergency response.

## Five-bus grid model

The grid combines two dispatchable generators, wind, solar, a battery, five buses, six lines, customer loads, reactive support, transformer tap, and demand response. A DC power-flow model calculates line flow and loading after every change in injection or breaker topology. A reduced-order frequency state responds to active-power imbalance. Bus-voltage estimates respond to line stress, customer loading, tap position, and capacitor support.

Inputs include gas and hydro dispatch, battery power, capacitor support, transformer tap, demand response, and operator-confirmed line breakers. Outputs include reported and modelled frequency, generation, demand, served and unserved load, renewable production, battery state of charge, bus voltage, line flow, line loading, and reactive margin.

Included scenarios are normal dispatch, evening peak, generator trip, line trip, rapid solar loss, frequency sensor spoofing, and industrial overload. The spoofing exercise keeps the displayed measurement plausible while an independent dynamic estimate detects the disagreement.

AI can optimize dispatch, battery, flexible demand, tap position, and reactive support. It cannot issue relay or breaker commands. This mirrors the distinction between economic or supervisory operation and deterministic protection.

## Local LLM context and decision path

Ollama does not retain operating memory by itself. For each call, the supervisor assembles current sensors, alarms, controls, permitted ranges, and the previous audited decision. That bounded context creates explicit short-term memory. It can be inspected and replaced without relying on hidden model state.

```text
Live simulation state + prior audited decision
                    |
                    v
        Ollama strict JSON proposal
                    |
                    v
      Pydantic structure validation
                    |
                    v
     Domain-specific deterministic gate
                    |
          advisory, shadow, reject,
          or one bounded application
```

If Ollama is unavailable or invalid, the UI labels and uses a deterministic fallback proposal. The fallback passes through the same gate. The decision panel always shows the source, proposed values, status, explanation, and rejection reasons.

The official sources behind the equipment selection and safety boundary are listed in [REFERENCES.md](REFERENCES.md).
