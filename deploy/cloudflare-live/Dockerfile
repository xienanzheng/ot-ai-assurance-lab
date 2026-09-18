FROM python:3.12-slim
WORKDIR /lab
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
COPY services/plant_sim/requirements.txt /tmp/plant.txt
COPY services/plc_control/requirements.txt /tmp/plc.txt
COPY services/supervisor/requirements.txt /tmp/supervisor.txt
RUN pip install --no-cache-dir -r /tmp/plant.txt -r /tmp/plc.txt -r /tmp/supervisor.txt
COPY shared /lab/shared
COPY services/plant_sim/app /lab/services/plant_sim/app
COPY services/plc_control/app /lab/services/plc_control/app
COPY services/infrastructure_sim/app /lab/services/infrastructure_sim/app
COPY services/supervisor/app /lab/services/supervisor/app
COPY deploy/cloudflare-live/start.py /lab/start.py
RUN useradd --create-home lab && chown -R lab:lab /lab
USER lab
ENV PYTHONPATH=/lab PYTHONUNBUFFERED=1 \
    PLANT_API_URL=http://127.0.0.1:8081 PLC_API_URL=http://127.0.0.1:8082 \
    INFRASTRUCTURE_API_URL=http://127.0.0.1:8083 \
    OPCUA_URL=opc.tcp://127.0.0.1:4840/waterlab/server/ \
    DATABASE_URL=sqlite:////lab/session.db \
    HOSTED_MODE=true LESSON_MEMORY_ENABLED=false WATCHER_ENABLED=false \
    OLLAMA_BASE_URL=http://inference.lab OLLAMA_MODEL=@cf/qwen/qwen3-30b-a3b-fp8
EXPOSE 8080
CMD ["python", "/lab/start.py"]
