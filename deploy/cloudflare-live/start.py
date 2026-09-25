"""One complete simulated lab per container; no shared database or host mounts."""
import signal
import subprocess
import sys
import time
import urllib.request

processes=[]
def stop(*_):
    for process in processes:
        if process.poll() is None: process.terminate()
    for process in processes:
        try: process.wait(timeout=8)
        except subprocess.TimeoutExpired: process.kill()
    sys.exit(0)

signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
try:
    for service,port in [('plant_sim',8081),('plc_control',8082),('infrastructure_sim',8083),('supervisor',8080)]:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','0.0.0.0' if port==8080 else '127.0.0.1','--port',str(port)],cwd=f'/lab/services/{service}')
        processes.append(process)
        deadline=time.monotonic()+90
        while True:
            if process.poll() is not None: raise RuntimeError(f'{service} exited during startup')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=2) as response:
                    if response.status==200: break
            except (OSError,TimeoutError): pass
            if time.monotonic()>deadline: raise RuntimeError(f'{service} startup timed out')
            time.sleep(.3)
    # Defence in depth: even a leaked persistent connection cannot run forever.
    deadline=time.monotonic()+20*60
    while time.monotonic()<deadline:
        if any(p.poll() is not None for p in processes): raise RuntimeError('Lab service exited')
        time.sleep(1)
finally:
    stop()
