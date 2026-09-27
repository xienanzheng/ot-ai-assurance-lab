import math
import pytest
from services.supervisor.app.sop_context import response_window, select_sops, response_summary, temporal_check


def test_chlorine_response_window_uses_existing_simulator_coefficient():
    window=response_window('water',{'chlorine_target_mg_l':1.3})
    assert window['observe_minutes']==12
    assert window['lease_minutes']>=window['observe_minutes']+1
    assert window['basis']=='simulator_coefficients_not_physical_calibration'
    assert response_window('water',{'pressure_target_m':46})['observe_minutes']==5


def test_sops_are_domain_scoped_versioned_and_bound_to_signals():
    state={'sensors':{'chlorine_residual_mg_l':{'value':.3,'quality':'good'}},'active_alarms':[{'code':'LOW_CHLORINE'}]}
    context=select_sops('water',state)
    assert context['sha256'] and context['authority']=='context_only'
    assert any(s['id']=='water.disinfection' for s in context['procedures'])
    assert all(s['domain']=='water' for s in context['procedures'])
    assert all(s['source'] for s in context['procedures'])


def test_response_summary_uses_simulation_time_and_exposes_insufficient_data():
    assert response_summary([])['status']=='insufficient_observations'
    samples=[{'minute':i,'values':{'level':40+i*.2}} for i in range(5)]
    summary=response_summary(samples)
    assert summary['signals']['level']['slope_per_simulated_minute']==pytest.approx(.2)
    assert summary['signals']['level']['n']==5
    assert summary['causal_claim'] is False


def test_temporal_gate_blocks_early_change_but_not_hold_or_later_change():
    prior={'applied_minute':10,'observe_minutes':12,'before_targets':{'chlorine_target_mg_l':1},'applied_targets':{'chlorine_target_mg_l':1.2}}
    assert temporal_check(15,{'chlorine_target_mg_l':1.3},prior)
    assert not temporal_check(15,{},prior)
    assert not temporal_check(22,{'chlorine_target_mg_l':1.3},prior)
    assert temporal_check(22,{'chlorine_target_mg_l':.9},prior)
    assert not temporal_check(34,{'chlorine_target_mg_l':.9},prior)


def test_book_rejects_duplicate_and_cross_domain_identifiers():
    from copy import deepcopy
    from pydantic import ValidationError
    from services.supervisor.app.sop_context import ContextBook, load_book
    book = load_book()
    duplicate = deepcopy(book)
    duplicate['procedures'].append(duplicate['procedures'][0])
    with pytest.raises(ValidationError, match='unique'):
        ContextBook.model_validate(duplicate)
    book['procedures'][0]['domain'] = 'grid'
    with pytest.raises(ValidationError, match='match its domain'):
        ContextBook.model_validate(book)


def test_generated_book_matches_registry_and_sources_exist():
    from pathlib import Path
    from scripts.build_sop_book import OUTPUT, ROOT, render
    from services.supervisor.app.sop_context import load_book
    assert OUTPUT.read_text() == render()
    for procedure in load_book()['procedures']:
        assert (ROOT / procedure['source']).is_file()


def test_repeated_polling_does_not_count_as_new_observations():
    sample = {'minute': 1, 'values': {'level': 40}}
    assert response_summary([sample] * 5)['status'] == 'insufficient_observations'


def test_infrastructure_sop_signals_exist_in_live_contracts():
    from services.infrastructure_sim.app.grid import GridSimulator
    from services.infrastructure_sim.app.nuclear import NuclearSimulator
    from services.supervisor.app.sop_context import load_book
    snapshots={'grid':GridSimulator().snapshot(),'nuclear':NuclearSimulator().snapshot()}
    for procedure in load_book()['procedures']:
        if procedure['domain'] in snapshots:
            assert set(procedure['signals']) <= set(snapshots[procedure['domain']].sensors)
