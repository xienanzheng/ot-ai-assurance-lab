FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY services/supervisor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY shared /app/shared
COPY services/supervisor/app /app/app
COPY services/plc_control/app /app/plc_app
COPY services/infrastructure_sim/app /app/infra_app
COPY services/plant_sim/app/scenarios.py /app/plant_scenarios.py
COPY tests /app/tests
ENV PYTHONPATH=/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
