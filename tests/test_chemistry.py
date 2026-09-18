import pytest

from shared.chemistry import (
    alum_alkalinity_demand,
    free_chlorine_hocl_fraction,
    inorganic_carbon_mol_l,
    naoh_alkalinity_addition,
    ph_from_alkalinity,
    required_naoh_dose,
    solution_flow_lph,
)


def test_alum_consumes_and_naoh_restores_alkalinity():
    assert alum_alkalinity_demand(20.0) == 10.0
    assert naoh_alkalinity_addition(8.0) == 10.0


def test_carbonate_solver_round_trip():
    inorganic_carbon = inorganic_carbon_mol_l(7.35, 55.0)
    assert ph_from_alkalinity(55.0, inorganic_carbon) == pytest.approx(7.35, abs=0.001)


def test_required_naoh_dose_links_alum_and_target_ph():
    dose = required_naoh_dose(7.35, 55.0, 22.0, 7.35)
    assert dose == pytest.approx(8.8, abs=0.2)


def test_hocl_fraction_falls_as_ph_rises():
    assert free_chlorine_hocl_fraction(7.0) > free_chlorine_hocl_fraction(8.0)


def test_flow_paced_solution_rate_conserves_chemical_mass():
    assert solution_flow_lph(280.0, 8.0, 320.0) == pytest.approx(7.0)
