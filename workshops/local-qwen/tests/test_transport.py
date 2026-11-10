import asyncio
import socket
import pytest
from v2.controller import Controller
from v2.journal import Journal
from v2.packages import load_package
from v2.opcua import OpcSource, serve_opc


def freeport():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]


async def test_real_opc_capture_and_disconnect():
    p=load_package('water'); c=Controller(p,Journal('sqlite://'))
    endpoint=f'opc.tcp://127.0.0.1:{freeport()}/v2'
    async with serve_opc(c,endpoint):
        async with OpcSource(endpoint) as source:
            first=await source.capture(p)
            assert first.readings['chlorine_residual'].value==1.4
            c.inject('bad_sensor'); await asyncio.sleep(.3)
            second=await source.capture(p)
            assert second.readings['chlorine_residual'].quality=='bad'
            assert second.received_at>=second.source_time
            assert second.connection_epoch
            with pytest.raises(Exception,match='BadUserAccessDenied|BadNotWritable'):
                await source.node.write_value('{}')
            with pytest.raises(ValueError,match='package mismatch'):
                await source.capture(load_package('cooling'))
    with pytest.raises(Exception):
        async with OpcSource(endpoint) as source: await source.capture(p)


async def test_scan_recovers_from_storage_failure_without_faking_freshness():
    from contextlib import suppress
    from v2.controller_service import scan_loop
    c=Controller(load_package('water'),Journal('sqlite://'))
    original=c.journal.put_many
    def fail(entries): raise OSError('disk temporarily unavailable')
    c.journal.put_many=fail
    task=asyncio.create_task(scan_loop(c,.01))
    try:
        await asyncio.sleep(.04)
        assert not task.done()
        assert c.snapshot().readings['chlorine_residual'].quality=='bad'
        timestamp=c.snapshot().source_time
        await asyncio.sleep(.03)
        assert c.snapshot().source_time==timestamp
        c.journal.put_many=original
        await asyncio.sleep(.04)
        assert c.snapshot().readings['chlorine_residual'].quality=='good'
        assert c.snapshot().sequence>0
        assert not c.snapshot().armed
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError): await task


def test_receiver_requires_identity_and_rejects_external_host():
    from fastapi.testclient import TestClient
    from v2.controller_service import make_app,ReceiverClient
    c=Controller(load_package('water'),Journal('sqlite://'))
    token='test-local-receiver-token-long-enough'
    client=TestClient(make_app(c,token))
    assert client.post('/arm/off').status_code==403
    assert client.post('/arm/off',headers={'X-V2-Token':token}).status_code==200
    with pytest.raises(ValueError,match='local simulated receiver'):
        ReceiverClient('http://plant.example:502',token)
