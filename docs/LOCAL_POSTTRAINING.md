# What we trained, and how to learn from it

The browser lab, the local training code and Cloudflare inference are separate. Installing the lab starts a stock model. Nothing automatically promotes a trained adapter into control.

| Work | What changed | Weight updates? | Status |
|---|---|---|---|
| SOP/context engineering | Sensor facts, quality, age, alarms, history and response delays in the prompt | No | Used by the application |
| Structured decisions | JSON contracts, bounded targets and independent validation | No | Used by the application |
| Water Jev teacher pilot | Independently checked teacher choices became supervised training targets | Local 4B only | Completed; failed readiness |
| Typed Qwen workshop | LoRA on a frozen 4-bit 4B base, learning one decision label per example | Yes | Completed; failed readiness |
| Cloud Qwen30B demonstrations | Four verified examples added to its input | No | Tested; not adopted |
| RL / DPO | Proposed reward/preference follow-up | No | Not executed |
| Gemma auditor | Prompted review of proposal and evidence | No | No auditor fine-tuning claimed |

## The latest reproducible workshop

The [standalone package](../workshops/local-qwen/QUICKSTART.md) includes water/cooling SOP JSON, case generation, a scorer, unit tests, training code and saved evaluation rows. Use it to follow:

```text
Simulated snapshots + SOPs
  → frozen train / validation / test cases
  → base-model evaluation
  → one LoRA run
  → checkpoint selection on validation
  → matched test + failure review
```

The model scores labels for code-authored hold, adjust and escalate options. Code supplies JSON structure, bounded targets and evidence templates. This is narrower than unrestricted diagnosis or natural-language control.

Training used 384 available training cases, 48 validation cases and 96 test cases. The bounded run made 128 batch-one updates, consuming 128 examples—not all 384. It trained four layers, rank eight, at `5e-5`, with prompt-masked label loss and gradient checkpointing. This is supervised low-rank adaptation over a quantized base; it does not reproduce every detail of the original QLoRA method.

| Same 96 test cases | Base 4B | LoRA candidate |
|---|---:|---:|
| Correct status and target | 32/96 | 41/96 |
| Correct decision and supported reason | 8/96 | 34/96 |
| Correct holds | 32/32 | 0/32 |
| Correct adjustments | 0/32 | 27/32 |
| Correct escalations | 0/32 | 14/32 |
| Median forward pass | 4.163 s | 4.178 s |
| p95 forward pass | 9.211 s | 10.640 s |

The candidate improved some decisions but lost all legitimate holds. It stays offline. There is **no measured inference-speed gain**. The timings exclude model loading, auditing and plant response. See [full protocol and limitations](../workshops/local-qwen/docs/TYPED_QWEN_EXPERIMENT.md).

## Did we use distillation?

In the earlier water pilot, Jev selected from bounded options. An independent SOP scorer accepted 113 of 128 responses; balancing produced 96 training examples. Those accepted choices trained a new 4B adapter. This is teacher-assisted supervised distillation of choices, not hidden-reasoning transfer or token-distribution distillation. Code expanded the selected choice into the structured training target.

On 32 development cases, local decision correctness rose from 8/32 to 17/32, but correct holds fell from 8/8 to 0/8. The pilot failed its readiness screen. The later typed workshop did **not** use the separate Claude drafts in its weights. Paid teacher access is unnecessary for the packaged workshop; the historical Jev collector and its private raw artifacts are not included here.

## What friends can change

Start by inspecting `process_packages/water.json`, `training/bench_cases.py` and `training/typed_policy.py`. Check why a case should hold before changing its label. Add tests for alternative valid targets, stale data, bad flow and pending observation windows.

After inspecting the published test results, those cases are learning material, not a fresh blind test. For a new hypothesis, version the generator, choose new episode seeds/variants and freeze new splits before training. Compare both the base and candidate on the same cases. Keep failures in the denominator. Do not replace the active provider from an aggregate accuracy score.

References: [MLX-LM adaptation guide](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md), [QLoRA](https://arxiv.org/abs/2305.14314). The [training guide](../workshops/local-qwen/TRAINING.md) gives the actual package commands and environment pins.
