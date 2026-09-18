# Technical references

These primary sources informed the simulation design. The lab values remain illustrative and are not copied regulatory limits.

- [US EPA EPANET](https://www.epa.gov/water-research/epanet): extended-period hydraulic and water-quality simulation for pipes, nodes, pumps, valves, tanks, and reservoirs.
- [EPANET 2.2 user manual](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10113EM.txt): valve types, valve settings, shutoff valves, check valves, flow, and head-loss behavior.
- [US EPA WNTR hydraulic simulation](https://usepa.github.io/WNTR/hydraulics.html): pressure-dependent demand, leaks, EPANET simulation, and hydraulic equations.
- [US EPA WNTR controls](https://usepa.github.io/WNTR/controls.html): condition-based pump, pipe, and valve actions with control priority.
- [US EPA online water-quality monitoring guidance](https://www.epa.gov/sites/default/files/2018-05/documents/owqm-ds_guidance_042018.pdf): monitoring at distribution entry points, storage, booster stations, critical customers, and low-residual areas.
- [US EPA high-quality turbidity data guidance](https://www.epa.gov/sdwa/generating-high-quality-turbidity-data-drinking-water-treatment-plants-support-system): treatment-plant turbidimeters and SCADA data quality.
- [US EPA drinking-water treatment technologies](https://www.epa.gov/sdwa/overview-drinking-water-treatment-technologies): caustic soda use for pH adjustment and corrosion control.
- [US EPA Water Treatment Plant Model manual](https://www.epa.gov/sites/default/files/2017-03/documents/wtp_model_v._2.0_manual_508.pdf): sodium hydroxide alkalinity addition, carbonate chemistry, and chlorine CT calculations.
- [US EPA Surface Water Treatment Rule turbidity guidance](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P100ZLYM.txt): coagulation pH, chemical order, and separation of coagulant and alkalinity feed points.
- [US EPA disinfection profiling guidance](https://www.epa.gov/sites/default/files/2020-06/documents/disprof_bench_3rules_final_508.pdf): theoretical detention time, clearwell baffling factors, T10, and calculated CT.
- [OPC Foundation online reference](https://reference.opcfoundation.org/): data access, alarms and conditions, historical access, programs, and state machines.
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs): schema-constrained local model responses.
- [Ollama context length](https://docs.ollama.com/context-length): context-window configuration and memory use.
- [Ollama embeddings](https://docs.ollama.com/capabilities/embeddings): optional future semantic retrieval for larger memory collections.
- [US EPA EPANET-RTX utility support story](https://19january2021snapshot.epa.gov/emergency-response-research/simulating-conditions-drinking-water-utilities_.html): linking SCADA with an EPANET model for real-time utility analysis.
- [Bentley OpenFlows WaterSight](https://www.bentley.com/software/openflows-watersight/): connected SCADA, GIS, hydraulic models, customer data, asset history, anomaly detection, and scenario analysis.
- [Autodesk InfoWater Pro SCADA runs](https://help.autodesk.com/cloudhelp/ENU/INFWP-UserGuide/files/GUID-D7884798-E663-4354-8DA0-4B474CC30224.htm): telemetry boundary conditions, measured-model comparison, continuous verification, and event replay.
- [Siemens SIMIT](https://www.siemens.com/en-us/products/simit/): real-time plant simulation, virtual commissioning, and operator training.
- [Rockwell Automation PlantPAx instructions](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/37-00/contents-ditamap/instruction-set/plantpax-instructions.html): process objects for permissives, interlocks, PID control, dosing, valves, lead-lag equipment, restart inhibition, runtime, and start counting.
- [Rockwell Automation PlantPAx Process Application Development Library](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/proces-rm215_-en-p.pdf): stateful process-control patterns and operator-facing diagnostics used as a reference for the simulated PLC hierarchy.

## Nuclear generation

- [INL Human System Simulation Laboratory](https://inl.gov/human-factors/hssl/): public capabilities for configurable control rooms, advanced alarms, automated control, predictive maintenance, operational visualization, computerized procedures, and operator studies.
- [INL Flexible Plant Operation and Generation](https://lwrs.inl.gov/flexible-plant-operation-and-generation/): research on thermal and electrical dispatch, control interfaces, and associated safety assessments.
- [INL NPP Simulators for Coupled Thermal and Electric Power Dispatch](https://lwrs.inl.gov/content/uploads/11/2024/08/Vendor-NPP-Simulator_Final.pdf): public report on generic PWR and BWR simulator modifications, reduced-order and full-scope tools, operator-in-the-loop evaluation, and heat dispatch to an industrial process.
- [INL RELAP5-3D](https://inl.gov/relap53d/): official capability and licensing page. It identifies RELAP5-3D as a thermal-hydraulic and kinetics code distributed under license and export review. This lab does not include or reproduce it.
- [INL Plant Modernization](https://lwrs.inl.gov/about/plant-modernization/): public research program covering digital technologies, automation, and modernized plant operations.
- [US NRC pressurized-water reactor overview](https://www.nrc.gov/reactors/power/pwrs): primary coolant loop, reactor vessel, steam generator, pressurizer, turbine generator, condenser, and feedwater arrangement.
- [US NRC PWR process diagram](https://www.nrc.gov/reactors/pwrs.pdf): official visual reference for the primary and secondary loops used in the control-room mimic.
- [US NRC Reactor Concepts Manual](https://www.nrc.gov/sites/default/files/doc_library/cdn/legacy/reading-rm/training/reactor-concepts-training-course.pdf): reactor systems, operating variables, protection, heat transfer, steam cycle, and safety functions.
- [IAEA Design of Instrumentation and Control Systems for Nuclear Power Plants](https://nucleus.iaea.org/sites/nss-oui/Published%20Collections/m_3df5a9eb-7e9b-4968-a0d6-4864db84d434/m_3df5a9eb-7e9b-4968-a0d6-4864db84d434__18_0.Html): safety classification, automatic and manual safety actions, main control room, human factors, and historical data.
- [IAEA Artificial Intelligence for Accelerating Nuclear Applications, Science and Technology](https://www-pub.iaea.org/MTCD/Publications/PDF/ART-INTweb.pdf): AI use for anomaly detection, inspection, decision support, and physics-based modelling.
- [IAEA Nuclear Safety Review 2024](https://www.iaea.org/sites/default/files/gc/gc68-inf-4.pdf): current operating-plant AI applications remain independent of safety-related systems and functions.
- [US NRC Digital Instrumentation and Control Reference Guide](https://www.nrc.gov/reactors/digital/refguide): regulatory and technical references for nuclear digital instrumentation and control.

## Electric power grid

- [US Department of Energy electric grids](https://www.energy.gov/topics/electric-grids): generation, transmission, distribution, transformers, sensors, software, and communications.
- [US Department of Energy essential reliability services](https://www.energy.gov/cmei/articles/keeping-lights-essential-reliability-services): supply-demand balance, frequency response, voltage control, reactive power, and transformer settings.
- [US Department of Energy Electricity Grid Backgrounder](https://www.energy.gov/sites/default/files/2023-11/FINAL_CESER%20Electricity%20Grid%20Backgrounder_508.pdf): substations, transformers, relays, breakers, switches, feeders, and instrumentation.
- [PNNL GridLAB-D](https://www.pnnl.gov/available-technologies/gridlab-dtm): time-series distribution simulation for loads, distributed energy resources, controls, and reliability studies.
- [NREL grid modeling tools](https://www.nrel.gov/grid/modeling-tools): power-system planning, operations, integration, and analysis tools.
- [US Department of Energy solar grid planning and operation](https://www.energy.gov/cmei/systems/solar-grid-planning-and-operation-basics): balancing, protection, situational awareness, sensing, and real-time control with variable generation.
- [PNNL integrated transmission and distribution control](https://www.pnnl.gov/publications/integrated-transmission-and-distribution-control): coordinated transmission and distribution control research.
