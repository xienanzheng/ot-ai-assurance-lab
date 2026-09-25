# Digital twin benchmark

This note compares WaterLab with real water digital-twin and operator-training systems. It keeps a strict distinction between the local simulated lab and an operational twin connected to a utility.

## What working water twins usually contain

EPA's EPANET-RTX work linked raw SCADA signals to an EPANET hydraulic model so utilities could evaluate current conditions, identify low pressure, and investigate water age. Bentley OpenFlows WaterSight combines SCADA, GIS, hydraulic models, customer information, and asset history, then compares present, historical, and forecast performance. Autodesk InfoWater uses telemetry for boundary conditions, continuous model verification, gap analysis, and scenario replay. Siemens SIMIT represents process, device, signal, and controller behavior for virtual commissioning and operator training.

The recurring pattern is:

```text
Asset and network definition
        +
Reviewed telemetry and boundary conditions
        |
        v
Time-synchronized process and hydraulic model
        |
        +--> measured versus modeled validation
        +--> current-state estimation
        +--> forecast and scenario branches
        +--> operator or optimizer recommendation
        +--> governed control path and audit record
```

## WaterLab alignment

| Capability | WaterLab now | Needed for an operational twin |
| --- | --- | --- |
| Dynamic time | Resettable plant-owned clock, pause, step, 1x, 10x, and 60x | Synchronization to utility time sources and late-data handling |
| Process model | Dynamic treatment chemistry, storage, pumps, valves, alarms, and feed equipment | Calibration from plant design data, tests, and operating history |
| Hydraulic model | WNTR pressure-dependent demand, tanks, pumps, PRV, TCVs, leakage, and five-minute solves | Full GIS-derived network, elevations, pipe properties, demands, and field calibration |
| Telemetry | Simulated OPC UA sensor values with quality and timestamp | Read-only gateway to reviewed SCADA, historian, meters, laboratory, and asset systems |
| Model validation | Pressure RMSE, flow residual, source label, fit status, and sync age | Acceptance thresholds, drift workflow, calibration ownership, and approved data corrections |
| Scenarios | Repeatable faults and controller-mode comparisons with fixed seeds | Utility event library, approved initial conditions, and incident replay |
| Controls | PLC-only OPC UA writer, supervisory targets, deterministic gate, and emergency fallback | Independent safety assessment, authentication, change control, and site acceptance testing |
| AI | Structured local proposals, bounded memory, shadow and gated modes | Extended shadow evaluation, operator governance, monitoring, and model risk management |
| Spatial context | Three-zone schematic | GIS map, asset identifiers, topology validation, and customer impact analysis |
| Water quality | pH, alkalinity, turbidity, chlorine residual, HOCl fraction, T10, and CT | Calibrated reactions, water age, source tracing, laboratory reconciliation, and approved CT method |

## Current classification

WaterLab is a software-in-the-loop operator-training and control-research twin. It has a simulated plant, simulated telemetry, a virtual PLC-style controller, OPC UA coupling, a historian, fault injection, and model validation. It is not yet an operational digital twin because it is not synchronized with a physical utility, GIS, or field telemetry.

This classification matches Siemens' warning that a simulation twin models real behavior with limited accuracy and is intended for a non-critical environment. It also matches the telemetry-first pattern described by EPA, Autodesk, and Bentley.

## Best next fidelity upgrades

1. Import a small EPANET INP and GIS asset table with stable asset IDs.
2. Add water age and source tracing throughout the three zones.
3. Build a historical telemetry replay adapter using CSV before considering any live connector.
4. Add a measured-versus-modeled calibration report for flow, pressure, tank level, and chlorine residual.
5. Add pump curves, efficiency surfaces, electricity tariffs, valve failure modes, and chemical tank inventory.
6. Validate treatment coefficients against bench data and validate T10 with a tracer-study dataset.
7. Keep AI in shadow mode until repeated runs show bounded, explainable, and operationally useful behavior.

## Primary references

- [US EPA EPANET-RTX utility support story](https://19january2021snapshot.epa.gov/emergency-response-research/simulating-conditions-drinking-water-utilities_.html)
- [Bentley OpenFlows WaterSight](https://www.bentley.com/software/openflows-watersight/)
- [Autodesk InfoWater Pro SCADA runs](https://help.autodesk.com/cloudhelp/ENU/INFWP-UserGuide/files/GUID-D7884798-E663-4354-8DA0-4B474CC30224.htm)
- [Autodesk InfoWater Pro overview](https://www.autodesk.com/products/infowater-pro/overview)
- [Siemens SIMIT](https://www.siemens.com/en-us/products/simit/)
- [Siemens SIMIT operating manual](https://cache.industry.siemens.com/dl/files/325/109996325/att_1346169/v1/SIMIT_enUS_en-US.pdf)
