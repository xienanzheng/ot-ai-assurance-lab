from fastapi.testclient import TestClient
from tests.test_feedback import setup
from v2.api import make_app


def test_api_refuses_arbitrary_providers_and_targets():
    c,s=setup(); client=TestClient(make_app(s))
    assert client.post('/api/analysis',json={'provider':'bad','apply':True}).status_code==400
    assert client.post('/api/analysis',json={'provider':'fixture','apply':True,'endpoint':'http://evil'}).status_code==422
    assert client.post('/api/arm',json={'policy':'bad'}).status_code==422
    assert client.post('/api/arm',json={'policy':'off'},headers={'Origin':'https://evil.test'}).status_code==403


def test_api_export_and_status_are_generic():
    c,s=setup(); client=TestClient(make_app(s))
    data=client.get('/api/status').json()
    assert data['package']['id']=='water'
    assert data['capture_error']=='Connecting'
    assert client.get('/api/export').json()['schema_version']=='1'


def test_read_only_profile_never_sends_control_requests():
    c,s=setup(); client=TestClient(make_app(s,read_only=True))
    before=c.snapshot().generation
    for path,body in [('arm',{'policy':'off'}),('scenario',{'name':'reset'}),('analysis',{'provider':'fixture','apply':True}),('feedback',{'provider':'fixture','apply':True})]:
        assert client.post('/api/'+path,json=body).status_code==403
    assert client.post('/api/stop').status_code==200
    assert c.snapshot().generation==before


async def test_startup_waits_for_receiver_then_recovers_disarmed():
    import httpx
    from v2.api import recover_with_retry
    c,s=setup(); c.arm('off'); original=s.receiver.stop; attempts=[]
    async def starting():
        attempts.append(1)
        if len(attempts)<3:raise httpx.ConnectError('Receiver still starting')
        return await original()
    s.receiver.stop=starting
    await recover_with_retry(s,attempts=3,interval=0)
    assert len(attempts)==3 and not c.snapshot().armed


async def test_startup_failure_is_bounded():
    import httpx,pytest
    from v2.api import recover_with_retry
    c,s=setup(); calls=[]
    async def offline():
        calls.append(1);raise httpx.ConnectError('Receiver offline')
    s.receiver.stop=offline
    with pytest.raises(httpx.ConnectError):await recover_with_retry(s,attempts=2,interval=0)
    assert len(calls)==2


async def test_duplicate_api_job_is_rejected_and_export_preserves_evidence():
    import asyncio,httpx
    from v2.providers import FixtureProvider
    c,s=setup(); await s.observe(c.snapshot())
    entered=asyncio.Event(); release=asyncio.Event()
    class Pending(FixtureProvider):
        async def decide(self,context):
            entered.set();await release.wait();return await super().decide(context)
    s.providers['pending']=Pending()
    transport=httpx.ASGITransport(app=make_app(s))
    async with httpx.AsyncClient(transport=transport,base_url='http://localhost') as client:
        assert (await client.post('/api/analysis',json={'provider':'pending'})).status_code==202
        await asyncio.wait_for(entered.wait(),2)
        assert (await client.post('/api/analysis',json={'provider':'pending'})).status_code==409
        release.set()
        for _ in range(100):
            if not s.busy:break
            await asyncio.sleep(.01)
        exported=(await client.get('/api/export')).json()
        assert len(exported['records'])==1
        record=exported['records'][0]
        assert record['input']['snapshot']['generation']==c.snapshot().generation
        assert record['proposal']['target']==1.0
        assert record['status']=='evaluated' and record['command'] is None
