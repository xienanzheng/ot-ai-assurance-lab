import json
import httpx
import pytest
from tests.test_feedback import setup
from v2.contracts import Proposal,digest
from v2.providers import OllamaProvider


def test_request_uses_focused_state_without_decision_labels():
    c,s=setup();model=OllamaProvider('http://localhost','qwen3:4b')
    request=model.decision_request(s.context(c.snapshot()))
    data=json.loads(request['messages'][-1]['content'])
    assert data['observation']['active'] is False
    assert data['objective']['target_position']=='above'
    assert 'expected' not in data
    assert request['options']['temperature']==0


async def test_audit_binds_hash_in_code_and_preserves_raw_review(monkeypatch):
    c,s=setup();context=s.context(c.snapshot())
    proposal=Proposal(status='hold',rationale='Waiting',evidence=['chlorine_residual'])
    reply={'status':'flagged','reason':'Residual 1.4 exceeds 1.1; no wait is active.'}
    async def handler(request):return httpx.Response(200,json={'message':{'content':json.dumps(reply)}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    result,trace=await OllamaProvider('http://localhost','gemma3:4b').audit_with_evidence(context,proposal)
    assert result.status=='flagged'
    assert result.proposal_hash==digest({'snapshot':context['snapshot'],'proposal':proposal.model_dump()})
    assert trace['deterministic_findings'][0]['issue']=='unsupported_hold'
    assert json.loads(trace['raw_response']['message']['content'])==reply
    assert 'proposal_hash' not in trace['request']['format']['properties']


def test_contradictory_audit_status_and_issue_are_invalid():
    from v2.providers import AuditVerdict
    with pytest.raises(ValueError):AuditVerdict(status='passed',issue='unsupported_hold',reason='No active wait')
