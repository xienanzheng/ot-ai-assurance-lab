FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY services/watcher_relay/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/watcher_relay/app /app/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
