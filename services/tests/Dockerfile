FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
COPY services/plant_sim/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/supervisor/requirements.txt /tmp/supervisor.txt
RUN pip install --no-cache-dir -r /tmp/supervisor.txt
COPY shared /app/shared
COPY services /app/services
COPY tests /app/tests
COPY scripts /app/scripts
COPY config /app/config
COPY pyproject.toml /app/pyproject.toml
ENV PYTHONPATH=/app
CMD ["pytest", "-q"]
