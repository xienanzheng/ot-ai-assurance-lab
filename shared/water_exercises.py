"""Display objectives tied to the simulator's limits, not regulatory thresholds."""
from shared.limits import LIMITS, CHLORINE_RESIDUAL_ALARMS

WATER_EXERCISES = {
    'chlorine_efficiency_trim': {
        'name': 'Chlorine residual adjustment',
        'signal': 'chlorine_residual_mg_l', 'measurement': 'Chlorine residual', 'unit': 'mg/L',
        'operating_band': list(LIMITS['chlorine_residual_mg_l']),
        'alarm_thresholds': dict(CHLORINE_RESIDUAL_ALARMS),
        'optimization_band': [0.9, 1.0],
        'target': 'chlorine_target_mg_l', 'target_label': 'Residual target', 'target_unit': 'mg/L',
        'note': 'The efficiency band is narrower than the operating limits. The baseline PLC target is 1.15 mg/L.',
    },
    'chlorine_overdose': {
        'name': 'Chlorine overdose',
        'signal': 'chlorine_residual_mg_l', 'measurement': 'Chlorine residual', 'unit': 'mg/L',
        'operating_band': list(LIMITS['chlorine_residual_mg_l']),
        'alarm_thresholds': dict(CHLORINE_RESIDUAL_ALARMS),
        'target': 'chlorine_target_mg_l', 'target_label': 'Residual target', 'target_unit': 'mg/L',
        'note': 'Overfeed starts at minute 10. Inspect the feed mismatch and operator recommendations; critical conditions block AI actuation.',
    },
    'gradual_turbidity_rise': {
        'name': 'Rising filtered-water turbidity',
        'signal': 'filtered_turbidity_ntu', 'measurement': 'Filtered-water turbidity', 'unit': 'NTU',
        'operating_band': list(LIMITS['filtered_turbidity_ntu']),
        'target': 'coagulant_target_mg_l', 'target_label': 'Coagulant PLC target', 'target_unit': 'mg/L',
        'note': 'Source turbidity rises from minute 10. Observe the filtered-water response; chlorine protection remains active.',
    },
}
