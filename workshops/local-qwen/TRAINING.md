# Offline post-training, step by step

This recipe reproduces the **procedure** from the typed Qwen experiment. It does not promise identical numbers on another computer. It never applies model proposals to a process or replaces your Ollama model.

## Environment

Use an Apple Silicon Mac and Python 3.13. The recorded machine was an Apple M4 with 24 GB unified memory; peak logged training memory was 3.955 GB, excluding other applications and operating-system overhead. That is an observation, not a minimum-RAM guarantee. Initial setup needs internet and several GB of free disk space. The six experiment stages subsequently run offline.

From this workshop directory:

```sh
python3.13 -m venv .venv-train
.venv-train/bin/python -m pip install -r requirements-training.txt
.venv-train/bin/python -m pytest -q
.venv-train/bin/python scripts/download_training_model.py
```

The requirements pin the MLX/MLX-LM/Transformers/NumPy/Hugging Face versions recorded locally. If those versions are unavailable for your platform, stop and record the dependency error; do not silently upgrade and call it the same experiment. The download uses revision `4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25` of `mlx-community/Qwen3-4B-4bit` in your standard home cache. Review the model's upstream license before redistributing weights.

Before GPU work, stop your own live feedback and other model/training jobs. Do not change source files, dependencies or the model cache between experiment stages: each stage verifies their hashes or versions.

## Six stages

Run once per stage, from this directory. Choose a new output directory. `caffeinate -i` keeps a Mac awake during each command; keep the lid open.

```sh
TRAIN_PY="$PWD/.venv-train/bin/python"
MODEL="$HOME/.cache/huggingface/hub/models--mlx-community--Qwen3-4B-4bit/snapshots/4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25"
EXPERIMENT_ROOT='artifacts/my-first-typed-run'
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1

caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage prepare --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage baseline --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage train --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage validate --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage test --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage report --root "$EXPERIMENT_ROOT" --model "$MODEL"
```

| Stage | Output / purpose |
|---|---|
| prepare | 384/48/96 frozen cases; prompts, menus, labels, hashes and settings |
| baseline | Base model on validation; no weight changes |
| train | 128 LoRA updates; checkpoints at 64 and 128 |
| validate | Both checkpoints on validation; selects without test results |
| test | Base and selected adapter on the same 96 cases, sequentially |
| report | `summary.json`, readiness checks and `failures.json` |

Training uses four layers, rank 8, batch 1, `5e-5`, seed 42, checkpointing, and loss on the selected label token only. The 128-update cap is one third of an epoch over the 384-case training corpus. No teacher API, online RL or visitor data is used in this recipe.

## Read the results

Inspect `summary.json`: compare hold, adjust and escalate separately; check supported reasons, unavailable responses and median/p95 latency. Inspect incorrect records in `failures.json`, including actions that would violate protection even if a downstream gate could reject them.

Readiness requires zero protection/prerequisite misses, at least 90% correct status/target, supported reasons and holds, at least four more correct cases than base, complete matching, and median/p95 no more than 1.10× base. These are research thresholds, not operational certification. The historical adapter failed. The CLI has **no promotion or deployment command**.

If a stage fails, preserve its `.started.json`, partial rows and any failure record. Resource failures abort instead of continuing on an unreliable GPU backend. Do not delete the claim to retry a wrong answer or overwrite the original run. Diagnose separately and use a newly named experiment for a deliberate rerun. A failed setup may also leave a partially created output directory.

The published 96 test cases have already been inspected. Replaying them teaches the workflow; it does not provide new blind-test evidence. Before a new improvement study, version `training/bench_cases.py`, define new episode seeds/scenario variants and freeze them before training. Preserve the original benchmark.

## What is and is not included

- Included: source, package SOPs, tests, original historical evaluation rows and human-readable results.
- Generated locally: datasets, prompts, manifests, model outputs and adapter checkpoints.
- Downloaded separately: pinned base model and Python/container dependencies.
- Not included: private credentials, visitor details, personal slides, old adapter weights, private teacher prompts or a physical-plant driver.

`SOURCE.json` records the original V2 source hashes at revision `9278a4c`. Packaging changes use `Path.home()` instead of a personal model path, include `training` in Python package discovery, add Linux Docker host mapping, strengthen ignore rules, remove trailing whitespace and add these instructions/helper scripts. The npm starter adds a separate `ot-qwen-workshop` Compose project, development proxy and optional command wrappers; it does not change the training objective. Original measured model results belong to revision `20a709f`, before a resource-error handling fix. No GPU rerun is claimed for the packaged copy.

Official method reference: [MLX-LM LoRA guide](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md). The [historical report](docs/TYPED_QWEN_EXPERIMENT.md) explains limitations, training imbalance and proposed next experiments.
