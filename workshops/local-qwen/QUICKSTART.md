# Local Qwen workshop

Three ways to use this package:

| Goal | Needs | Start |
|---|---|---|
| Read cases, score results, run checks | Python 3.12 or 3.13 | Section 1 |
| Try the water/cooling bench | Docker; Ollama optional | Section 2 |
| Train your own research adapter | Apple Silicon Mac; Python 3.13; MLX | [Training guide](TRAINING.md) |

For the larger water/nuclear/grid application, use the [main lab guide](https://github.com/xienanzheng/ot-ai-assurance-lab/blob/docs/friends-quickstart/docs/QUICKSTART.md). This workshop is a standalone V2 package with simpler water/cooling dynamics.

## 1. Install and inspect

From your repository clone:

```sh
cd workshops/local-qwen
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python scripts/review_saved_results.py
```

Use `python3.12` if that is your installed version. On Windows, use `py -3.13 -m venv .venv`, then `.venv\Scripts\python.exe` for the commands above. The CPU checks do not require MLX, Ollama, a GPU or API keys. The original training environment used Python 3.13; Python 3.14 is not the documented target.

The result command recomputes the historical metrics from 192 saved simulated evaluation records and verifies their hashes. It makes no model calls. Inspect the procedure and thresholds in [the experiment report](docs/TYPED_QWEN_EXPERIMENT.md).

Generate a readable case set without a model:

```sh
.venv/bin/python -c "from pathlib import Path; from training.bench_cases import freeze_dataset; freeze_dataset(Path('artifacts/learning-cases'))"
```

Open `artifacts/learning-cases/train.jsonl`. Each record contains a package, snapshot, prerequisites, recent history, expected disposition and acceptable targets. The output directory must be new; existing experiments are not overwritten.

Useful files:

| File | Purpose |
|---|---|
| `process_packages/water.json` | Units, response time, observation window, SOP and bounded controls |
| `process_packages/cooling.json` | Same contract for temperature control |
| `training/bench_cases.py` | Case generator, independent labels, leakage checks and scorer |
| `training/typed_policy.py` | Model input, typed choices and decoded JSON |
| `training/mlx_experiment.py` | Baseline, LoRA training, selection and matched test |
| `v2/decision_context.py` | Live context and evidence construction |
| `v2/providers.py` | Qwen provider and Gemma audit prompts |
| `tests/` | Contract, gate, timing, audit and experiment tests |

## 2. Run the local bench

Open Docker Desktop. From `workshops/local-qwen`:

```sh
python3 scripts/preflight.py --init
docker compose up -d --build --wait --wait-timeout 300
```

Open **http://localhost:18790**. The first build downloads dependencies and images. The initializer writes fresh private `.env` credentials; it never copies Isaac's credentials.

1. Select **New bench session**, then **Load exercise**.
2. Select **fixture**, audit **off**, arm control, enable application and run once.
3. Compare the proposal, gate decision, controller acknowledgement and readback.
4. Observe gradual response: water starts at 1.4 mg/L; fixture requests 1.0 mg/L. The fixture checks integration, not AI accuracy.

To try a real local model:

```sh
ollama pull qwen3:4b
ollama pull gemma3:4b
```

Keep native Ollama running. Choose **qwen**; Gemma is optional. Audit **observe** reviews after evaluation/application; **required** needs a passed audit before submission. Neither mode bypasses the deterministic gate. This bench uses stock Ollama weights, not the experimental MLX adapter.

On native Linux, the Docker bridge must be able to reach Ollama at `host.docker.internal:11434`. The package supplies that hostname mapping; Ollama's default loopback listener may still need adjustment. Do not expose it to the public internet. CPU-only users can use fixtures for the bench and the offline case tests without changing a listener.

The response constant is 60 seconds; the next action waits 90 seconds after an accepted change. Leave time to observe. See [the runbook](docs/RUNBOOK.md) for cooling, fault injects, feedback and exports.

Stop with `docker compose down`; data stays in its own V2 volume. Port 18790 is the web UI; 18840 is simulated OPC UA, both loopback-bound. No physical equipment connection is configured.

## 3. Train separately

Follow [TRAINING.md](TRAINING.md). Do not run training alongside live model inference on a memory-constrained laptop. The supplied training path is for Apple Silicon; Windows/Linux users can inspect cases and run the simulator, but there is no tested CUDA training recipe in this package.

Published source is MIT-licensed; model weights retain their provider's license. The download retrieves weights from their upstream repository, rather than redistributing a fine-tuned model.
