# Run the lab on your computer

For editable React frontends and npm commands, use the [developer quick start](DEVELOPMENT.md). The Docker-first path below does not require Node.js.

Start here if you want to try the water, nuclear and grid simulators. No API key or paid service is required for local Qwen. The model and container images download on first setup.

## 1. Install prerequisites

- [Docker Desktop](https://docs.docker.com/compose/install/) and Git. Open Docker Desktop before continuing.
- [Ollama](https://docs.ollama.com/quickstart) for local inference. Open the app; use a **local** model.
- Python 3.10+ for the configuration helper below.

macOS and Windows: use Docker Desktop. Windows: run the commands in PowerShell, with `python` instead of `python3` if needed. Linux: use Docker Engine with the Compose plugin. Native Linux Ollama may need configuration to accept connections from the Docker bridge; the container option below avoids that change.

Plan for several GB of downloads. The recorded training machine had 24 GB unified memory; training requirements and simulator requirements are different. Smaller computers can start with rule-based controls or the lightweight workshop fixtures.

## 2. Get the shareable version

```sh
git clone --branch docs/friends-quickstart https://github.com/xienanzheng/ot-ai-assurance-lab.git
cd ot-ai-assurance-lab
python3 scripts/setup_local.py
```

The helper creates `.env` with a random local database password and `qwen3:4b`. It preserves an existing `.env`. It does not install software, pull a model or start services.

## 3. Start Qwen and the simulator

```sh
ollama pull qwen3:4b
ollama list
docker compose up -d --build --wait --wait-timeout 300
```

If Ollama is not running, open its desktop app or run `ollama serve` in another terminal. Do not start a second server if one already owns port 11434.

Open **http://localhost:18780**. The page is local to your computer.

First exercise:

1. Open **AI decisions / Local AI agents → Water exercise**.
2. Choose **Chlorine residual adjustment**, then **Qwen**.
3. Run one analysis; inspect the JSON, gate result and applied target separately.
4. Open the water HMI and watch the residual respond over simulated time.
5. Choose at least two calls and **Start monitoring & control** for repeated observations. Export the session JSON when done.

For an initial rule-based run, skip Ollama and use baseline control. AI analysis will report unavailable until the configured model is running. This clone uses stock Qwen; it does not load a research adapter.

## Optional: auditor

```sh
ollama pull gemma3:4b
```

Set `DECISION_AUDIT_ENABLED=true` in `.env`, then recreate the supervisor:

```sh
docker compose up -d --force-recreate supervisor-api
```

In this main lab, the reviewer runs in the background; it does not replace the deterministic gate. The [V2 workshop](../workshops/local-qwen/QUICKSTART.md) separately demonstrates off/observe/required audit modes.

## Linux or no native Ollama

Set `OLLAMA_BASE_URL=http://ollama:11434` in `.env`, then:

```sh
docker compose --profile ollama-container up -d --build --wait --wait-timeout 300
docker compose --profile ollama-container exec ollama ollama pull qwen3:4b
```

This profile does not configure GPU passthrough; CPU inference may be slow. Apple Silicon GPU inference uses native Ollama, not this container.

## Check, stop and troubleshoot

```sh
docker compose ps
docker compose logs --tail 80 supervisor-api
docker compose down
```

`down` preserves records. Adding `--volumes` deletes the local database.

| Symptom | Check |
|---|---|
| Cannot connect to Docker | Start Docker Desktop; run `docker info`. |
| Port 18780 already used | Stop your other lab instance; do not run both on the same port. |
| Model not found | `ollama list`; ensure `.env` names the model you pulled. |
| Inference unavailable | Ollama must be reachable from the supervisor container, not only your browser. Check its logs. |
| First call is slow | Model loading adds latency; avoid running training and live inference together. |
| Proposal rejected | Read the gate reason: stale state, observation window, critical alarms and missing prerequisites still block application. |
| Model download blocked | Initial setup requires internet; installed weights can later run locally. |

For model development, continue with the [post-training overview](LOCAL_POSTTRAINING.md) and [standalone workshop](../workshops/local-qwen/QUICKSTART.md). This package runs simulated processes; it supplies no physical-plant installation or actuation adapter.
