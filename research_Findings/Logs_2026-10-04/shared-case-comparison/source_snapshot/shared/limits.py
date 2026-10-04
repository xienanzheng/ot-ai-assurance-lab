"""Illustrative simulation limits. These are not regulatory requirements."""

LIMITS = {
    "clearwell_level_pct": (25.0, 92.0),
    "elevated_tank_level_pct": (25.0, 95.0),
    "zone_pressure_m": (25.0, 65.0),
    "chlorine_residual_mg_l": (0.2, 4.0),
    "filtered_turbidity_ntu": (0.0, 1.0),
    "coagulation_ph": (5.5, 8.2),
    "finished_water_ph": (6.5, 9.2),
    "finished_alkalinity_mg_l_caco3": (20.0, 150.0),
    "chlorine_ct_mg_min_l": (20.0, 400.0),
    "pump_speed_pct": (0.0, 100.0),
    "valve_position_pct": (5.0, 100.0),
    "intake_gate_position_pct": (20.0, 100.0),
    "filter_outlet_valve_position_pct": (15.0, 100.0),
    "zone_isolation_valve_position_pct": (30.0, 100.0),
    "chlorine_dose_mg_l": (0.0, 5.0),
    "coagulant_dose_mg_l": (0.0, 60.0),
    "naoh_dose_mg_l": (0.0, 25.0),
}

SETPOINT_LIMITS = {
    "clearwell_target_pct": (45.0, 80.0),
    "elevated_tank_target_pct": (45.0, 85.0),
    "pressure_target_m": (35.0, 55.0),
    "chlorine_target_mg_l": (0.5, 2.0),
    "coagulant_target_mg_l": (8.0, 45.0),
    "finished_water_ph_target": (7.0, 8.8),
    "intake_gate_target_pct": (30.0, 100.0),
    "filter_outlet_valve_target_pct": (30.0, 100.0),
    "zone_1_isolation_target_pct": (50.0, 100.0),
    "zone_2_isolation_target_pct": (50.0, 100.0),
    "zone_3_isolation_target_pct": (50.0, 100.0),
}

MAX_SETPOINT_STEP = {
    "clearwell_target_pct": 5.0,
    "elevated_tank_target_pct": 5.0,
    "pressure_target_m": 4.0,
    "chlorine_target_mg_l": 0.25,
    "coagulant_target_mg_l": 5.0,
    "finished_water_ph_target": 0.20,
    "intake_gate_target_pct": 15.0,
    "filter_outlet_valve_target_pct": 15.0,
    "zone_1_isolation_target_pct": 15.0,
    "zone_2_isolation_target_pct": 15.0,
    "zone_3_isolation_target_pct": 15.0,
}

VALVE_TRAVEL_RATE_PCT_MIN = 12.0
