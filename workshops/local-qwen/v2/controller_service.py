import asyncio
from contextlib import asynccontextmanager, suppress
import os
import secrets
import time
import httpx
from fastapi import FastAPI, Header, HTTPException, Depends
from .contracts import CommandRequest, Snapshot
from .controller import Controller
from .journal import Journal
from .packages import load_package
from .opcua import serve_opc


def make_app(controller,token):
    if len(token)<24: raise ValueError('Service token required')
    async def auth(x_v2_token: str=Header(default='')):
        if not secrets.compare_digest(x_v2_token,token): raise HTTPException(403,'Invalid receiver identity')
    app=FastAPI(dependencies=[Depends(auth)])
    @app.get('/snapshot')
    async def snapshot(): return controller.snapshot()
    @app.post('/apply')
    async def apply(request:CommandRequest): return controller.apply(request)
    @app.get('/commands/{command_id}')
    async def status(command_id:str): return controller.status(command_id)
    @app.post('/arm/{policy}')
    async def arm(policy:str):
        try: return controller.arm(policy)
        except ValueError as e: raise HTTPException(409,str(e))
    @app.post('/stop')
    async def stop(): return controller.stop()
    @app.post('/scenario/{name}')
    async def scenario(name:str):
        try: return controller.reset() if name=='reset' else controller.inject(name)
        except ValueError as e: raise HTTPException(400,str(e))
    return app


async def scan_loop(controller, interval=1):
    last=time.monotonic()
    while True:
        await asyncio.sleep(interval)
        now=time.monotonic(); elapsed=now-last; last=now
        try:
            if elapsed>5: controller.stop()
            controller.step(min(elapsed,600))
        except Exception as error:
            # Even if persistence is unavailable, inhibit in-memory authority.
            controller.scan_error=str(error)[:300]
            controller.state={**controller.state,'armed':False}


def factory():
    journal=Journal(os.environ['DATABASE_URL'])
    # Exactly one controller instance owns the bench database at a time.
    lock_connection=journal.engine.connect()
    if journal.engine.dialect.name=='postgresql':
        from sqlalchemy import text
        if not lock_connection.execute(text('SELECT pg_try_advisory_lock(187901)')).scalar():
            raise RuntimeError('Controller already running')
    controller=Controller(load_package(os.getenv('PROCESS_PACKAGE','water')),journal)
    app=make_app(controller,os.environ['SERVICE_TOKEN'])
    @asynccontextmanager
    async def lifespan(app):
        async with serve_opc(controller,'opc.tcp://0.0.0.0:4840/v2'):
            task=asyncio.create_task(scan_loop(controller))
            try: yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError): await task
                lock_connection.close()
    app.router.lifespan_context=lifespan
    return app


class ReceiverClient:
    def __init__(self,url,token):
        from urllib.parse import urlparse
        if urlparse(url).hostname not in ('controller','127.0.0.1','localhost'):
            raise ValueError('Only the local simulated receiver is supported')
        self.client=httpx.AsyncClient(base_url=url,headers={'X-V2-Token':token},timeout=5)
    async def apply(self,request):
        r=await self.client.post('/apply',json=request.model_dump()); r.raise_for_status(); return r.json()
    async def status(self,id):
        r=await self.client.get('/commands/'+id); r.raise_for_status(); return r.json()
    async def snapshot(self):
        r=await self.client.get('/snapshot'); r.raise_for_status(); return Snapshot.model_validate(r.json())
    async def arm(self,policy):
        r=await self.client.post('/arm/'+policy); r.raise_for_status(); return r.json()
    async def stop(self):
        r=await self.client.post('/stop'); r.raise_for_status(); return r.json()
    async def scenario(self,name):
        r=await self.client.post('/scenario/'+name); r.raise_for_status(); return r.json()
