import json
from copy import deepcopy
import httpx
import pytest
from tests.test_feedback import setup
from v2.contracts import Proposal
from v2.providers import OllamaProvider
from v2.decision_context import decision_view


def test_schema_binds_sensor_and_operator_ids_to_package():
    c,s=setup();model=OllamaProvider('http://localhost','qwen3:4b')
    body=model.decision_request(s.context(c.snapshot()))
    assert set(body['format']['properties']['evidence']['items']['enum'])=={'chlorine_residual','flow'}
    assert set(body['format']['properties']['operator_checks']['items']['enum'])==set(c.package.checks)


def test_settling_requires_observed_progress_at_same_target():
    c,s=setup();context=s.context(c.snapshot());now=context['snapshot']
    now['target']=1.0;now['process_time']=20
    old=deepcopy(now);old['process_time']=10;old['readings']['chlorine_residual']['value']=1.5
    context['recent_observations']=[old]
    assert decision_view(context)['trend']['approaching_objective'] is True
    context['recent_observations'][0]['target']=1.2
    assert decision_view(context)['trend']['reliable'] is False


def test_no_trend_inference_from_bad_or_reversed_observations():
    c,s=setup();context=s.context(c.snapshot());now=context['snapshot'];now['process_time']=20
    old=deepcopy(now);old['process_time']=10;old['readings']['chlorine_residual']['quality']='bad'
    context['recent_observations']=[old]
    assert decision_view(context)['trend']['reliable'] is False
    old['readings']['chlorine_residual']['quality']='good';old['process_time']=30
    assert decision_view(context)['trend']['reliable'] is False


async def test_unknown_reference_from_provider_fails_runtime_validation(monkeypatch):
    c,s=setup();reply={'status':'hold','target':None,'rationale':'Inside band','evidence':['chlorine_residual: good'],'operator_checks':[]}
    async def handler(request):return httpx.Response(200,json={'message':{'content':json.dumps(reply)}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(ValueError,match='reference'):
        await OllamaProvider('http://localhost','qwen3:4b').decide(s.context(c.snapshot()))


async def test_audit_cannot_pass_protected_hold_and_keeps_model_verdict(monkeypatch):
    c,s=setup();context=s.context(c.snapshot());context['snapshot']['trip_latched']=True
    proposal=Proposal(status='hold',rationale='Everything is normal',evidence=['chlorine_residual'])
    async def handler(request):return httpx.Response(200,json={'message':{'content':json.dumps({'status':'passed','reason':'Normal reading'})}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    result,trace=await OllamaProvider('http://localhost','gemma3:4b').audit_with_evidence(context,proposal)
    assert result.status=='flagged'
    assert 'trip_latched' in result.reason
    assert trace['model_verdict']['status']=='passed'
    assert trace['deterministic_findings'][0]['issue']=='protection_active'
    assert trace['verdict_source']=='deterministic checks'


async def test_audit_parse_failure_has_short_reason_and_full_evidence(monkeypatch):
    c,s=setup();proposal=Proposal(status='hold',rationale='Wait')
    raw={'message':{'content':'not JSON'}}
    async def handler(request):return httpx.Response(200,json=raw)
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    result,trace=await OllamaProvider('http://localhost','gemma3:4b').audit_with_evidence(s.context(c.snapshot()),proposal)
    assert result.status=='unavailable' and len(result.reason)<100
    assert trace['raw_response']==raw and trace['seconds']>=0
    assert trace['error']


@pytest.mark.parametrize('status,target,change,expected',[
    ('adjust',1.0,{},[]),
    ('adjust',1.4,{},['recovery_interval','wrong_direction']),
    ('hold',None,{},['unsupported_hold']),
    ('hold',None,{'wait_until':90},[]),
    ('adjust',1.0,{'wait_until':90},['waiting']),
    ('escalate',None,{'override':True},[]),
    ('hold',None,{'override':True},['protection_active']),
    ('escalate',None,{},['unsupported_escalation']),
])
def test_factual_checks_distinguish_useful_actions_and_legitimate_holds(status,target,change,expected):
    from v2.decision_checks import proposal_findings
    c,s=setup();context=s.context(c.snapshot());context['snapshot'].update(change)
    p=Proposal(status=status,target=target,rationale='Example',evidence=['chlorine_residual'],operator_checks=['verify_protection'] if status=='escalate' else [])
    assert [f['issue'] for f in proposal_findings(context,p)]==expected


def test_gate_blocks_wrong_direction_even_with_audit_off():
    from tests.test_controller import setup as controller_setup, request
    c=controller_setup();before=c.snapshot().target
    result=c.apply(request(c,1.4))
    assert result['status']=='rejected'
    assert 'direction' in result['reason'].lower()
    assert c.snapshot().target==before


def test_schema_handles_all_missing_sensors_without_invalid_empty_enum():
    c,s=setup();context=s.context(c.snapshot());context['snapshot']['readings']={}
    schema=OllamaProvider('http://localhost','qwen3:4b').decision_request(context)['format']
    assert schema['properties']['evidence']['maxItems']==0
    assert 'enum' not in schema['properties']['evidence']['items']


async def test_one_correction_pass_keeps_original_and_revised_reply(monkeypatch):
    c,s=setup();context=s.context(c.snapshot());requests=[]
    replies=[{'status':'hold','target':None,'rationale':'Wait','evidence':['chlorine_residual'],'operator_checks':[]},
             {'status':'adjust','target':1.0,'rationale':'Reduce elevated residual','evidence':['chlorine_residual'],'operator_checks':[]}]
    async def handler(request):
        requests.append(json.loads(request.content));return httpx.Response(200,json={'message':{'content':json.dumps(replies[min(len(requests)-1,1)])}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    model=OllamaProvider('http://localhost','qwen3:4b')
    p=await model.decide(context)
    assert p.status=='adjust' and p.target==1.0 and len(requests)==2
    assert 'unsupported_hold' in requests[1]['messages'][-1]['content']
    assert len(model.last_decision_trace['attempts'])==2
    assert json.loads(model.last_decision_trace['attempts'][0]['raw_response']['message']['content'])['status']=='hold'
    assert model.last_decision_trace['attempts'][1]['findings']==[]


async def test_bad_second_reply_does_not_trigger_unbounded_retries(monkeypatch):
    c,s=setup();count=0
    async def handler(request):
        nonlocal count
        count+=1
        return httpx.Response(200,json={'message':{'content':json.dumps({'status':'hold','target':None,'rationale':'Wait','evidence':['chlorine_residual'],'operator_checks':[]})}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    model=OllamaProvider('http://localhost','qwen3:4b');proposal=await model.decide(s.context(c.snapshot()))
    assert count==2 and proposal.status=='hold'
    assert model.last_decision_trace['attempts'][-1]['findings']


def test_auditor_gets_proposed_target_comparisons_not_just_raw_arithmetic():
    c,s=setup();p=Proposal(status='adjust',target=1.0,rationale='Reduce residual',evidence=['chlorine_residual'])
    body=OllamaProvider('http://localhost','gemma3:4b').audit_request(s.context(c.snapshot()),p)
    view=json.loads(body['messages'][-1]['content'])['proposal_comparisons']
    assert view['target_position']=='inside'
    assert view['target_in_allowed_interval'] is True
    assert view['target_change']==pytest.approx(-.2)
    assert view['corrective_direction'] is True
    assert 'expected_verdict' not in view


@pytest.mark.parametrize('domain,value,current,bad,good',[
    ('water',1.4,1.2,1.4,1.0),
    ('water',.7,.8,.8,1.0),
    ('cooling',14,12,13,11),
    ('cooling',9,10,9,11),
])
def test_gate_direction_is_symmetric_across_bench_packages(domain,value,current,bad,good):
    from tests.test_controller import setup as controller_setup,request
    c=controller_setup(domain);c.state.update(value=value,target=current)
    assert c.apply(request(c,bad))['status']=='rejected'
    assert c.apply(request(c,good))['status']=='applied'


def test_audit_generation_uses_binary_verdict_not_fault_classification():
    c,s=setup();proposal=Proposal(status='escalate',rationale='Trip requires operator',operator_checks=['verify_protection'])
    schema=OllamaProvider('http://localhost','gemma3:4b').audit_request(s.context(c.snapshot()),proposal)['format']
    assert set(schema['properties'])=={'status','reason'}
    assert set(schema['properties']['status']['enum'])=={'passed','flagged'}


def test_context_exposes_interior_goal_and_nominal_response_time():
    c,s=setup();view=decision_view(s.context(c.snapshot()))
    assert view['response_planning']['objective_midpoint']==pytest.approx(1.025)
    assert view['response_planning']['reachable_goal_this_step']==pytest.approx(1.025)
    assert 90<view['response_planning']['nominal_seconds_to_band']<100
    assert view['response_planning']['assumption']


def test_boundary_target_is_not_mistaken_for_finite_recovery():
    from v2.decision_checks import proposal_findings
    c,s=setup();ctx=s.context(c.snapshot())
    p=Proposal(status='adjust',target=1.1,rationale='Reduce residual',evidence=['chlorine_residual'])
    assert any(f['issue']=='boundary_target' for f in proposal_findings(ctx,p))
    # A boundary target can be a necessary intermediate step when the interior is unreachable.
    ctx['snapshot']['target']=1.3
    assert not any(f['issue']=='boundary_target' for f in proposal_findings(ctx,p))


def test_hold_at_boundary_without_active_wait_requires_another_correction():
    from v2.decision_checks import proposal_findings
    c,s=setup();ctx=s.context(c.snapshot());now=ctx['snapshot'];now.update(target=1.1,process_time=100)
    now['readings']['chlorine_residual']['value']=1.15
    old=deepcopy(now);old['process_time']=90;old['readings']['chlorine_residual']['value']=1.17
    ctx['recent_observations']=[old]
    p=Proposal(status='hold',rationale='Settling',evidence=['chlorine_residual'])
    assert any(f['issue']=='unsupported_hold' for f in proposal_findings(ctx,p))


def test_generation_limits_rationale_without_breaking_historical_records():
    c,s=setup();schema=OllamaProvider('http://localhost','qwen3:4b').decision_request(s.context(c.snapshot()))['format']
    assert schema['properties']['rationale']['maxLength']==300
    assert Proposal(status='hold',rationale='x'*900).rationale


def test_controller_requires_primary_sensor_evidence_even_without_audit():
    from tests.test_controller import setup as controller_setup,request
    c=controller_setup();r=request(c)
    r=r.model_copy(update={'proposal':r.proposal.model_copy(update={'evidence':[]})})
    assert c.apply(r)['status']=='rejected'
    assert c.snapshot().target==1.2


def test_generated_targets_are_constrained_to_reachable_recovery_band():
    c,s=setup();body=OllamaProvider('http://localhost','qwen3:4b').decision_request(s.context(c.snapshot()))
    numeric=next(branch for branch in body['format']['properties']['target']['anyOf'] if branch['type']=='number')
    assert numeric['minimum']==pytest.approx(1.0)
    assert numeric['maximum']==pytest.approx(1.085)


def test_controller_rejects_boundary_when_interior_target_is_reachable():
    from tests.test_controller import setup as controller_setup,request
    c=controller_setup()
    result=c.apply(request(c,1.1))
    assert result['status']=='rejected'
    assert 'recovery interval' in result['reason'].lower()
    assert c.apply(request(c,1.025))['status']=='applied'


def test_controller_allows_necessary_intermediate_step():
    from tests.test_controller import setup as controller_setup,request
    c=controller_setup();c.state.update(target=1.3,value=1.5)
    assert c.apply(request(c,1.1))['status']=='applied'


def test_intermediate_candidates_are_correctly_directed_and_exhaustion_has_none():
    from v2.packages import candidate_targets
    c,s=setup();ctx=s.context(c.snapshot());ctx['snapshot']['target']=1.3
    assert all(t<1.3 for t in candidate_targets(ctx['package'],ctx['snapshot']))
    ctx['snapshot']['target']=.8
    assert candidate_targets(ctx['package'],ctx['snapshot'])==[]
