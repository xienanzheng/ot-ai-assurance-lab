"""Small carbonate and dosing calculations for the illustrative treatment model.

The equations conserve carbonate carbon and alkalinity, but they do not replace
site-specific jar tests, titrations, or a calibrated water-quality model.
"""

from __future__ import annotations

KA1 = 10**-6.35
KA2 = 10**-10.33
KW = 1e-14
MG_CACO3_PER_EQ = 50_000.0
ALUM_ALKALINITY_RATIO = 0.50
NAOH_ALKALINITY_RATIO = 50.0 / 40.0
ALUM_PRODUCT_G_L = 640.0
NAOH_SOLUTION_G_L = 320.0
HYPOCHLORITE_AVAILABLE_CHLORINE_G_L = 125.0


def carbonate_fractions(ph: float) -> tuple[float, float, float]:
    hydrogen = 10 ** (-ph)
    denominator = hydrogen**2 + KA1 * hydrogen + KA1 * KA2
    return (
        hydrogen**2 / denominator,
        KA1 * hydrogen / denominator,
        KA1 * KA2 / denominator,
    )


def inorganic_carbon_mol_l(ph: float, alkalinity_mg_l_caco3: float) -> float:
    """Infer dissolved inorganic carbon from pH and alkalinity."""
    hydrogen = 10 ** (-ph)
    _, bicarbonate, carbonate = carbonate_fractions(ph)
    alkalinity_eq_l = alkalinity_mg_l_caco3 / MG_CACO3_PER_EQ
    return max(1e-8, (alkalinity_eq_l - KW / hydrogen + hydrogen) / (bicarbonate + 2 * carbonate))


def alkalinity_from_ph(ph: float, inorganic_carbon: float) -> float:
    hydrogen = 10 ** (-ph)
    _, bicarbonate, carbonate = carbonate_fractions(ph)
    alkalinity_eq_l = inorganic_carbon * (bicarbonate + 2 * carbonate) + KW / hydrogen - hydrogen
    return alkalinity_eq_l * MG_CACO3_PER_EQ


def ph_from_alkalinity(alkalinity_mg_l_caco3: float, inorganic_carbon: float) -> float:
    """Solve carbonate alkalinity for pH with a stable bisection search."""
    low, high = 4.0, 11.0
    target = max(0.1, alkalinity_mg_l_caco3)
    for _ in range(70):
        midpoint = (low + high) / 2
        if alkalinity_from_ph(midpoint, inorganic_carbon) < target:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2


def alum_alkalinity_demand(alum_dose_mg_l: float) -> float:
    """Return an illustrative alkalinity demand as mg/L CaCO3."""
    return max(0.0, alum_dose_mg_l) * ALUM_ALKALINITY_RATIO


def naoh_alkalinity_addition(naoh_dose_mg_l: float) -> float:
    """Convert pure NaOH dose to alkalinity as mg/L CaCO3."""
    return max(0.0, naoh_dose_mg_l) * NAOH_ALKALINITY_RATIO


def required_naoh_dose(
    raw_ph: float,
    raw_alkalinity_mg_l_caco3: float,
    alum_dose_mg_l: float,
    target_ph: float,
) -> float:
    inorganic_carbon = inorganic_carbon_mol_l(raw_ph, raw_alkalinity_mg_l_caco3)
    post_alum_alkalinity = max(0.1, raw_alkalinity_mg_l_caco3 - alum_alkalinity_demand(alum_dose_mg_l))
    target_alkalinity = alkalinity_from_ph(target_ph, inorganic_carbon)
    return max(0.0, (target_alkalinity - post_alum_alkalinity) / NAOH_ALKALINITY_RATIO)


def free_chlorine_hocl_fraction(ph: float, pka: float = 7.5) -> float:
    """Estimate the fraction of free chlorine present as hypochlorous acid."""
    return 1.0 / (1.0 + 10 ** (ph - pka))


def solution_flow_lph(process_flow_m3h: float, dose_mg_l: float, product_strength_g_l: float) -> float:
    """Convert a process dose and water flow into chemical solution flow."""
    if product_strength_g_l <= 0:
        raise ValueError("product strength must be positive")
    chemical_mass_g_h = max(0.0, process_flow_m3h) * max(0.0, dose_mg_l)
    return chemical_mass_g_h / product_strength_g_l


def carbonate_summary(ph: float, alkalinity_mg_l_caco3: float) -> str:
    """Compact diagnostic used in tests and notebooks."""
    inorganic_carbon = inorganic_carbon_mol_l(ph, alkalinity_mg_l_caco3)
    return f"pH {ph:.2f}, alkalinity {alkalinity_mg_l_caco3:.1f} mg/L as CaCO3, DIC {inorganic_carbon * 1000:.3f} mmol/L"
