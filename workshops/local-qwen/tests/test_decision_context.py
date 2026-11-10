from copy import deepcopy
from tests.test_feedback import setup


def test_decision_view_distinguishes_objective_bounds_and_inactive_wait():
    from v2.decision_context import decision_view
    c,s=setup();v=decision_view(s.context(c.snapshot()))
    assert v['observation']['remaining_seconds']==0
    assert v['observation']['active'] is False
    assert v['objective']['measurement_position']=='above'
    assert v['objective']['target_position']=='above'
    assert v['command_limits']['allowed_target_interval']==[1.0,1.4]
    assert v['command_limits']['lower_headroom']==.2


def test_view_preserves_protection_and_missing_measurements():
    from v2.decision_context import decision_view
    c,s=setup();context=s.context(c.snapshot())
    context['snapshot']['trip_latched']=True
    context['snapshot']['readings'].pop('chlorine_residual')
    context['eligibility']=['chlorine_residual: missing']
    v=decision_view(context)
    assert v['protection']['trip_latched'] is True
    assert v['measurement'] is None
    assert v['objective']['measurement_position']=='unknown'
    assert v['prerequisite_failures']==['chlorine_residual: missing']


def test_view_cumulative_bound_and_history_are_not_answer_labels():
    from v2.decision_context import decision_view
    c,s=setup();context=s.context(c.snapshot());context['snapshot']['target']=.8
    context['recent_observations']=[deepcopy(context['snapshot'])]
    v=decision_view(context)
    assert v['command_limits']['allowed_target_interval']==[.8,1.0]
    assert v['command_limits']['lower_headroom']==0
    assert 'expected' not in v and 'recommended_action' not in v
    assert v['recent_measurements'][0]['value']==1.4
