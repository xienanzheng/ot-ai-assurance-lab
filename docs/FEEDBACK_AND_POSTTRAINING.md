# SOP feedback and local post-training

## Try the feedback loop

1. Start the local lab and open **Local AI agents** (or **AI decisions** in a hosted build).
2. Select a domain and Qwen or Jev. Choose **AI calls**, from one to six.
3. Select **Start feedback**. This enables gated supervisory control but does not start the simulation clock.
4. Start or resume the plant from its HMI. Use 1× speed when local inference is slow; accelerated simulation can exceed the five-minute freshness limit before a proposed adjustment returns. The loop captures current readings and SOPs, calls the selected model, submits an explicit proposal to the gate and waits for its response window.
5. Inspect the waiting status, HMI targets, **Feedback observations**, decision records, **SOP context and sources**, and **Response observation window**.
6. Select **Stop feedback** to disarm the loop and return to baseline. Export the session JSON to retain the current loop state and decision records.

Changing models requires stopping the active loop first. Manual analysis, comparison and proposal application are blocked while feedback owns supervision. No plant reset occurs when selecting the next model. Existing Cloudflare inference quotas still apply; a local call budget cannot increase them.

## Timing and gates

The gate retains target allowlists, bounds, maximum steps, sensor prerequisites and protection checks. Temporal checks reject another adjustment before the preceding observation window and reject rapid reversals for an additional window. Hold decisions do not change targets.

Feedback leases use the server-calculated response window plus a small margin, capped at 30 simulated minutes. Single manual analyses retain their five-minute lease. A review window is an earliest review time, not a settling guarantee. See the [context book](PLANT_CONTEXT_BOOK.md).

Only one loop can start at once. Pausing the simulation prevents new calls; stopping disarms in-flight proposals and serializes baseline return against application. Reset, changed control mode, critical state, rejection, model escalation, inference failure, time limit or call exhaustion ends the loop. It does not automatically classify a healthy snapshot as proven recovery.

Observation history contains at most 24 selected signals and eight recent samples per request, with missing/bad-quality indicators. Repeated polling at the same simulated minute does not inflate the trend sample count. Fast Qwen prompts compress repeated history fields losslessly. Both providers receive SOP provenance, prior actions and feedback observations.

Feedback outcomes are sampled after the scheduled observation window, rather than treating the first subsequent minute as the completed response. Slopes and before/after measurements are descriptive; disturbances and baseline control prevent causal attribution.

## Local adapter experiment

The scripts below create a local Qwen3 4B LoRA candidate using a four-bit MLX base model. They do not modify Ollama or replace the deployed model. Model files, datasets and raw results remain under ignored `artifacts/posttraining/`.

```sh
.venv-posttrain/bin/python scripts/train_sop_adapter.py --train --iters 120
.venv-posttrain/bin/python scripts/evaluate_sop_adapter.py --fresh-seed 40002 --output sop-evaluation-120steps.json
```

Prerequisites: an Apple Silicon training environment with `mlx-lm[train]`, and the pinned model download manifest at `artifacts/posttraining/models.json`. The current manifest pins `mlx-community/Qwen3-4B-4bit` revision `4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25`. Keep this training environment separate from the simulator runtime.

The pilot uses 120 training, 24 validation and 24 test examples with disjoint seeds. They are rule-labelled, simulated instruction-following exercises for water disinfection: bounded increase/decrease, normal hold, waiting, unreliable sensor and missing flow proof. These curriculum rules are explicitly supplied in each example; they are not expert-certified treatment instructions or delayed plant outcome labels.

Evaluation compares exact proposed actions and episode status, JSON validity and latency. Critical-alarm overrides are an additional unseen challenge. The initial 24-step experiment informed the longer run; the latter uses a fresh set of seeds. These are small template-based checks, not an independent operational benchmark. Latency also reflects output length and caching; repeated production-length trials are required before claiming a deployment speedup.

No adapter is automatically promoted. Promotion requires full-context tests across domains, independent gate evaluation, disturbance trajectories, recovery and adverse-effect measurements, and a locked evaluation set. Jev benefits from context inputs; this work does not fine-tune its hosted weights. A BERT reranker and preference/RL training remain separate experiments, not deployed features.

## Verification boundaries

Real grid-gate tests use controlled provider responses to verify target application, early-repeat rejection, HMI state, observation waiting and lease release for both adapters. Separate live-provider checks establish connectivity and actual model behavior; they must not be described as evidence of successful recovery when a model only held its targets.

The local training pilot does not alter the hosted Qwen model, Cloudflare secret configuration or the public deployment. See [the experiment results](POSTTRAINING_RESULTS.md) for measured outcomes and remaining limitations.
