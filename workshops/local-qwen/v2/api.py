import asyncio
from contextlib import asynccontextmanager, suppress
import os
import time
import httpx
from urllib.parse import urlparse
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from .contracts import Contract
from .packages import load_package
from .journal import Journal
from .controller_service import ReceiverClient
from .opcua import OpcSource
from .providers import FixtureProvider, OllamaProvider
from .supervisor import Supervisor


class Analysis(Contract):
    provider: str = 'qwen'
    apply: bool = False


class Feedback(Analysis):
    limit: int = Field(default=6,ge=1,le=12)


class Arm(Contract):
    policy: Literal['off','observe','required']='off'


class Scenario(Contract):
    name: Literal['normal','drift','critical','no_flow','bad_sensor','stale_sensor','override','reset']


async def recover_with_retry(supervisor,attempts=30,interval=1):
    # Compose restart may start the app before the receiver is listening.
    # Retry only transport availability; invalid identity/storage errors stay visible.
    for attempt in range(attempts):
        try:
            await supervisor.recover()
            return
        except httpx.TransportError:
            if attempt==attempts-1:raise
            await asyncio.sleep(interval)


def make_app(supervisor,read_only=False):
    s=supervisor; app=FastAPI(); jobs=set()
    @app.middleware('http')
    async def local_origin(request:Request,call_next):
        origin=request.headers.get('origin')
        host=request.url.hostname
        if host not in ('localhost','127.0.0.1','testserver') or (origin and urlparse(origin).netloc!=request.url.netloc):
            return JSONResponse({'detail':'Local same-origin access only'},status_code=403)
        return await call_next(request)
    def controls():
        if read_only: raise HTTPException(403,'This profile is read-only')
    @app.get('/api/status')
    async def status():
        return dict(package=s.package.model_dump(),package_hash=s.package.fingerprint(),
            snapshot=s.latest.model_dump() if s.latest else None,history=s.history[-180:],
            capture_error=s.capture_error,busy=s.busy or bool(jobs),feedback=s.feedback,policy=s.policy,
            read_only=read_only,auditor=s.auditor.name,providers={k:v.name for k,v in s.providers.items()})
    @app.get('/api/records')
    async def records(): return s.records()
    @app.get('/api/export')
    async def export():
        return dict(schema_version='1',exported_at=time.time(),package=s.package.model_dump(),
                    package_hash=s.package.fingerprint(),records=s.records(),observations=s.journal.list('sample:'),events=s.journal.list('event:'))
    @app.post('/api/arm')
    async def arm(body:Arm):
        controls()
        try: await s.arm(body.policy)
        except ValueError as e: raise HTTPException(409,str(e))
        return {'status':'armed'}
    @app.post('/api/stop')
    async def stop():
        # Read-only profiles do not send even a stop to an external receiver.
        if read_only:
            s.feedback['active']=False; s.epoch+=1
        else: await s.stop()
        return {'status':'stopped'}
    @app.post('/api/scenario')
    async def scenario(body:Scenario):
        controls()
        if s.busy or jobs: raise HTTPException(409,'Stop and wait for analysis before changing exercises')
        await s.stop()
        result=await s.receiver.scenario(body.name)
        s.latest=None
        if body.name=='reset':
            for r in s.records():
                if r['status']=='unknown':
                    r['status']='abandoned_by_bench_reset'; s.save(r)
            s.history=[]
        return result
    @app.post('/api/analysis',status_code=202)
    async def analysis(body:Analysis):
        if body.provider not in s.providers: raise HTTPException(400,'Unknown provider')
        if body.apply: controls()
        if s.busy or jobs or s.feedback['active']: raise HTTPException(409,'Supervision already owned')
        if not s.latest: raise HTTPException(409,'Waiting for telemetry')
        async def run():
            try: await s.analyse(body.provider,body.apply)
            except Exception as e:
                s.journal.put_many({'job_error':{'error':str(e)[:500],'time':time.time()}})
        task=asyncio.create_task(run()); jobs.add(task); task.add_done_callback(jobs.discard)
        return {'status':'queued'}
    @app.post('/api/feedback')
    async def feedback(body:Feedback):
        if body.apply: controls()
        try: s.start_feedback(body.provider,body.limit,body.apply)
        except ValueError as e: raise HTTPException(409,str(e))
        return s.feedback
    app.state.supervisor=s
    if os.path.isdir('web/dist'): app.mount('/',StaticFiles(directory='web/dist',html=True),name='web')
    return app


def factory():
    package=load_package(os.getenv('PROCESS_PACKAGE','water'))
    journal=Journal(os.environ['DATABASE_URL'])
    receiver=ReceiverClient('http://controller:8092',os.environ['SERVICE_TOKEN'])
    ollama=os.getenv('OLLAMA_URL','http://host.docker.internal:11434')
    providers={'fixture':FixtureProvider(),'qwen':OllamaProvider(ollama,os.getenv('QWEN_MODEL','qwen3:4b'))}
    s=Supervisor(package,journal,receiver,providers,OllamaProvider(ollama,os.getenv('AUDIT_MODEL','gemma3:4b')))
    app=make_app(s)
    @asynccontextmanager
    async def lifespan(app):
        await recover_with_retry(s)
        async def capture():
            while True:
                try:
                    async with OpcSource('opc.tcp://controller:4840/v2') as source:
                        last_saved=0
                        while True:
                            snap=await source.capture(package); await s.observe(snap)
                            if snap.process_time-last_saved>=5:
                                journal.put_many({'sample:'+str(time.time_ns()):snap.model_dump()}); last_saved=snap.process_time
                            await asyncio.sleep(1)
                except asyncio.CancelledError: raise
                except Exception as e:
                    s.capture_error=str(e)[:300]
                    with suppress(Exception): journal.put_many({'event:'+str(time.time_ns()):{'type':'acquisition_gap','time':time.time(),'reason':s.capture_error}})
                    s.feedback['active']=False; s.epoch+=1
                    with suppress(Exception): await receiver.stop()
                    await asyncio.sleep(2)
        async def feedback_loop():
            while True:
                try: await s.feedback_tick()
                except Exception as e:
                    s.feedback.update(active=False,reason=str(e)[:300])
                await asyncio.sleep(1)
        tasks=[asyncio.create_task(capture()),asyncio.create_task(feedback_loop())]
        try: yield
        finally:
            for task in tasks: task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError): await task
            for task in list(s.jobs): task.cancel()
            await receiver.client.aclose()
    app.router.lifespan_context=lifespan
    return app
