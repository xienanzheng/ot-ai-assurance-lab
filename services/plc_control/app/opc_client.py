from __future__ import annotations

from datetime import datetime

from asyncua import Client, ua

from shared.models import ActuatorCommand, ControlMode, PlantSnapshot, SensorValue
from shared.opcua_nodes import ACTUATOR_NODES, NAMESPACE_URI, SENSOR_NODES


UNITS = {
    "raw_flow_m3h": "m3/h", "raw_turbidity_ntu": "NTU", "clarified_turbidity_ntu": "NTU",
    "raw_ph": "pH", "raw_alkalinity_mg_l_caco3": "mg/L as CaCO3", "coagulation_ph": "pH",
    "settled_alkalinity_mg_l_caco3": "mg/L as CaCO3", "finished_water_ph": "pH",
    "finished_alkalinity_mg_l_caco3": "mg/L as CaCO3", "water_temperature_c": "degC",
    "filtered_turbidity_ntu": "NTU", "filter_dp_kpa": "kPa", "clearwell_level_pct": "%",
    "clearwell_level_model_pct": "%", "clearwell_overflow_m3h": "m3/h",
    "chlorine_residual_mg_l": "mg/L", "chlorine_model_estimate_mg_l": "mg/L",
    "chlorine_dose_actual_mg_l": "mg/L", "distribution_flow_m3h": "m3/h",
    "coagulant_dose_actual_mg_l": "mg/L", "chemical_feed_flow_proof": "bool",
    "chlorine_contact_time_min": "min", "chlorine_ct_mg_min_l": "mg-min/L",
    "hocl_fraction_pct": "%", "alum_feed_runtime_min": "min", "chlorine_feed_runtime_min": "min", "naoh_feed_runtime_min": "min",
    "naoh_dose_actual_mg_l": "mg/L",
    "alum_solution_flow_lph": "L/h", "naoh_solution_flow_lph": "L/h", "hypochlorite_solution_flow_lph": "L/h",
    "alum_bulk_tank_level_pct": "%", "alum_day_tank_level_pct": "%",
    "alum_transfer_valve_position_pct": "%", "alum_injection_valve_position_pct": "%",
    "naoh_bulk_tank_level_pct": "%", "naoh_day_tank_level_pct": "%",
    "naoh_transfer_valve_position_pct": "%", "naoh_injection_valve_position_pct": "%",
    "hypochlorite_bulk_tank_level_pct": "%", "hypochlorite_day_tank_level_pct": "%",
    "hypochlorite_transfer_valve_position_pct": "%", "hypochlorite_injection_valve_position_pct": "%",
    "elevated_tank_level_pct": "%", "zone_1_demand_m3h": "m3/h", "zone_2_demand_m3h": "m3/h",
    "zone_3_demand_m3h": "m3/h", "zone_1_pressure_m": "m", "zone_2_pressure_m": "m",
    "zone_3_pressure_m": "m", "leak_flow_m3h": "m3/h", "energy_kw": "kW",
    "intake_upstream_pressure_m": "m", "intake_downstream_pressure_m": "m",
    "filter_inlet_pressure_kpa": "kPa", "filter_outlet_pressure_kpa": "kPa",
    "pump_discharge_pressure_m": "m", "pump_deadhead_pressure_kpa": "kPa", "distribution_header_pressure_m": "m",
    "intake_gate_position_pct": "%", "filter_outlet_valve_position_pct": "%",
    "zone_1_isolation_valve_position_pct": "%", "zone_2_isolation_valve_position_pct": "%",
    "zone_3_isolation_valve_position_pct": "%", "zone_1_valve_dp_kpa": "kPa",
    "zone_2_valve_dp_kpa": "kPa", "zone_3_valve_dp_kpa": "kPa",
    "zone_1_served_m3h": "m3/h", "zone_2_served_m3h": "m3/h", "zone_3_served_m3h": "m3/h",
}


class OpcActuatorClient:
    def __init__(self, url: str) -> None:
        self.url = url

    async def write(self, command: ActuatorCommand) -> None:
        async with Client(self.url) as client:
            index = await client.get_namespace_index(NAMESPACE_URI)
            for name, value in command.model_dump(exclude_none=True).items():
                if name not in ACTUATOR_NODES:
                    continue
                node = client.get_node(ua.NodeId(f"Actuators.{name}", index))
                await node.write_value(value)

    async def read_snapshot(self) -> PlantSnapshot:
        async with Client(self.url) as client:
            index = await client.get_namespace_index(NAMESPACE_URI)
            time_text = await client.get_node(ua.NodeId("System.simulation_time", index)).read_value()
            elapsed_minutes = await client.get_node(ua.NodeId("System.elapsed_minutes", index)).read_value()
            speed = await client.get_node(ua.NodeId("System.simulation_speed", index)).read_value()
            mode = await client.get_node(ua.NodeId("System.controller_mode", index)).read_value()
            scenario = await client.get_node(ua.NodeId("System.active_scenario", index)).read_value()
            safety_state = await client.get_node(ua.NodeId("System.alarm_state", index)).read_value()
            emergency = await client.get_node(ua.NodeId("System.emergency_stop", index)).read_value()
            sensors = {}
            for name in SENSOR_NODES:
                reading = await client.get_node(ua.NodeId(f"Sensors.{name}", index)).read_value()
                quality = await client.get_node(ua.NodeId(f"Sensors.{name}.quality", index)).read_value()
                sensors[name] = SensorValue(
                    value=float(reading),
                    unit=UNITS[name],
                    quality=quality,
                    timestamp=datetime.fromisoformat(str(time_text)),
                )
            actuators = {}
            for name in ACTUATOR_NODES:
                actuators[name] = await client.get_node(ua.NodeId(f"Actuators.{name}", index)).read_value()
            return PlantSnapshot(
                simulation_time=datetime.fromisoformat(str(time_text)),
                elapsed_minutes=int(elapsed_minutes),
                simulation_speed=int(speed),
                running=True,
                scenario=str(scenario),
                controller_mode=ControlMode(str(mode)),
                sensors=sensors,
                equipment={},
                actuators=actuators,
                safety_state=str(safety_state),
                emergency_stop=bool(emergency),
            )
