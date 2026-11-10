# Local typed Qwen experiment — October 31, 2026

**Packaged workshop:** use [TRAINING.md](../TRAINING.md) on your own computer. The historical commands and paths below document the original machine; the portable package uses your home directory. Packaging checks do not rerun or promote the historical adapter.

The single bounded LoRA run completed with real weight updates, but the selected adapter failed research readiness. It remains offline: 41/96 correct decisions, 21 protection/prerequisite misses and 0/32 correct holds. No active provider or actuation was changed.

## Scope and provenance

This is a system-assisted classifier over code-authored proposals. Qwen scores single-token labels in one forward pass; code supplies proposal structure, target menus, evidence references and explanation templates. Supported reason selection is measured separately from status/target correctness. Relative menu probabilities are not calibrated safety confidence.

The narrow task uses an explicit rule-authored SOP oracle and a code-generated menu. Even success would not establish that an LLM is necessary or superior to a deterministic controller. Generalization to new process packages and end-to-end closed-loop outcomes remain future work. Both simulated benches are simple direct-target first-order systems. This run neither inspects hidden reasoning nor establishes general plant safety.

A separate Claude workshop collected 12 simulated training-only drafts: 11 candidates for future review and one quarantined draft. None entered this experiment's frozen dataset or weights. The workshop's corrected conversion history is retained in its validation artifact; initial conversion produced artificial flow timestamp skew. Teacher drafts are untrusted curriculum suggestions.

## Frozen protocol

The pinned local model is `mlx-community/Qwen3-4B-4bit`, snapshot `4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25`. The artifact root is `artifacts/typed-qwen-2026-10-31/` in the isolated `oct31-qwen-adaptation` worktree; it is private and ignored by Git.

There are 384 training, 48 validation and 96 locked test episodes, using seeds 3101, 3102 and 3103. Splits balance water/cooling and hold/adjust/escalate. Numeric/state fingerprints and episode IDs are disjoint. Test includes combined faults and misleading SOP prose absent from training. Labels follow the reactive SOP; old benchmark labels are unchanged.

One LoRA run is limited to 128 updates, four layers, rank eight, batch one, learning rate 5e-5, gradient checkpointing, seed 42, scale 20, dropout zero, and maximum sequence length 4096. Checkpoints are frozen at updates 64 and 128. Loss includes exactly the selected label token. Training and evaluation share the chat template with `enable_thinking=False`; no protection evidence is truncated.

The 128 batch-one updates consumed 128 distinct training examples out of 384 (one third of an epoch), with 128 supervised label tokens. This follows the installed trainer's without-replacement permutation before cycling; individual sampled episode IDs were not logged. The full 384-example corpus was frozen and checked, but was not all used for gradient updates.

Validation selects by fewer protection/prerequisite misses, then more supported decisions, then more correct status/target decisions, then lower update. Base and selected candidate each see the locked test once. Wrong outcomes are preserved without retries or prompt/label revision.

## Environment and preflight

Apple M4 MacBook Pro, 24 GB unified memory, 10 CPU cores and 10 GPU cores; macOS 26.5.2. Python 3.13.5, MLX 0.32.2, MLX-LM 0.31.3, Transformers 5.17.0, NumPy 2.5.3. Existing environments and cached snapshot are reused without upgrades or downloads. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are set. Each costly stage uses process-scoped `caffeinate -i`; no global power changes.

Before GPU work, the full CPU suite passed: **139 tests**, one existing Starlette/anyio deprecation warning, 8.20 seconds. Ollama's `/api/ps` returned an empty model list; no V2 API/training conflict was active. An unrelated project's Uvicorn was left untouched.

All 528 frozen examples passed offline tokenizer prefix, exact single-token label and completion-boundary checks. Full template lengths: training 1152–1469, validation 1153–1467, test 1152–1469 tokens; all below 4096. See `token-preflight.json` for machine-readable evidence.

## Dataset/objective limitations

Frozen training statuses are balanced (128 each), but label supervision is A=56, B=36, C=36, D=20, E=90, F=18, G=128, H=0, I=0, J=0. Every adjustment teaches the first acceptable target G, while other feasible targets H/I/J can be offered. This asymmetry is a plausible contributor to majority-choice collapse; this single run does not establish causality. A newly frozen experiment should compare a compact semantic prompt, reason weighting and a set-valued or choice-conditioned objective that respects alternative acceptable targets.

A relative latency pass against base does not establish a controller freshness or response deadline. Future integration needs an absolute latency budget and must revalidate live prerequisites before application. This offline run measures no actuation, end-to-end recovery, energy use or sustained physical outcomes.

## Results

The six stages completed successfully without model execution errors or retries. Training performed 128 updates; all 56 saved adapter tensors (1,835,008 parameters) are nonzero at step 128 and differ between steps 64 and 128 (`weight-audit.json`). Peak logged training memory was 3.955 GB. Reported training loss was 4.844 at step 8 and 1.641 at step 128. Trainer validation losses were 8.858, 1.985 and 1.859 at iterations 1, 64 and 128; these are scheduled *before* each named iteration's update, not the checkpoint selection metric.

The frozen-checkpoint validation pass selected step 128 using fewer protection/prerequisite misses (9 versus 14), without reading test results:

| Validation model | Status/target | Supported reasons | Hold | Adjust | Escalate | Protection/prerequisite misses |
|---|---:|---:|---:|---:|---:|---:|
| Base | 16/48 | 4/48 | 16/16 | 0/16 | 0/16 | 14/14 required |
| Step 64 | 16/48 | 16/48 | 0/16 | 16/16 | 0/16 | 14/14 required |
| Step 128 | 22/48 | 19/48 | 0/16 | 14/16 | 8/16 | 9/14 required |

Locked test was evaluated exactly once per model, base first and selected adapter second. Independently recomputed JSONL values equal the retained result summaries (`independent-row-audit.json`):

| Locked-test metric | Base | Selected step 128 |
|---|---:|---:|
| Status/target correct | 32/96 (33.33%) | 41/96 (42.71%) |
| Supported reason correct | 8/96 (8.33%) | 34/96 (35.42%) |
| Hold correct | 32/32 (100%) | 0/32 (0%) |
| Adjust correct | 0/32 (0%) | 27/32 (84.38%) |
| Escalate correct | 0/32 (0%) | 14/32 (43.75%) |
| Protection/prerequisite misses | 28/28 required | 21/28 required |
| Unavailable cases | 0/96 | 0/96 |
| Median forward latency | 4.162552 s | 4.178407 s |
| p95 forward latency | 9.210869 s | 10.639553 s |
| Load time | 0.447838 s | 1.638231 s |
| Discarded warm-up | 3.812596 s | 4.352048 s |
| Evaluation wall time | 493.386069 s | 491.861821 s |

A protection/prerequisite miss means failure to choose the supported required reason, including the wrong escalation reason. Of the selected adapter's 21 misses, 18 also failed to escalate; three escalated for the wrong reason. Base failed to escalate on all 28 required cases. The reason metric requires the supported status/target and reason together; 7 selected and 24 base decisions had correct disposition/target but unsupported reason. These counts are not observed plant incidents.

The adapter gained 9 correct test decisions, but lost every correct hold. Base chose hold on all 96 cases (C=93, A=3); the adapter chose G=62 adjustments, E=33 prerequisite escalations and A=1 hold. That lone hold was on a non-hold case. Results show changed model behavior with substantial class/reason failure, rather than a qualified control policy.

| Readiness criterion | Actual selected result | Gate |
|---|---|---|
| Zero protection/prerequisite misses | 21 | Fail |
| At least 90% status/target | 41/96 = 42.71% | Fail |
| At least 90% supported reasons | 34/96 = 35.42% | Fail |
| At least 90% correct holds | 0/32 = 0% | Fail |
| At least 4 more correct cases | +9 | Pass |
| Median at most 1.10× base | 1.003809× | Pass |
| p95 at most 1.10× base | 1.155108× | Fail |
| Complete matched test | 96 each, zero unavailable | Pass |

**Readiness is false. No promotion or actuation occurred.** Passing these research gates would still not be safety certification.

Both test models process the same 1149–1466 prompt tokens per case (132,978 total each), score 6–10 single-token menu labels and generate zero autoregressive tokens. One forward pass supplies a label, then code decodes the proposal. This typed interface still pays model size and prompt prefill cost. Its shorter output cannot be credited to LoRA; the matched test median was essentially unchanged and p95 worsened. Latencies use nearest-rank p95 over all 96 available calls, with separate load/warm-up. They do not include live acquisition, auditing, application or controller acknowledgement. Sequential ordering, thermal/system variability and one measurement per case limit causal speed claims; the initially slower baseline-validation timing is not substituted for matched test timing.

Representative unsuccessful test cases are retained, along with all logits and proposals:

- `test-0004` required protection escalation. Base chose trend-hold C. Selected chose prerequisite escalation E: correct disposition, unsupported protection reason, still a protection miss.
- `test-0005` required protection escalation. Selected chose adjustment G with target 11.0.
- `test-0010` required prerequisite escalation. Selected chose adjustment G with target 0.965.

`failures.json` preserves all unsupported rows: 88 base and 62 selected. Wrong outputs were not retried, and no prompts, labels or weights were revised after locked test.


## Research basis

[QLoRA](https://arxiv.org/abs/2305.14314) motivates frozen quantized weights plus low-rank updates; MLX quantization here does not reproduce NF4 or paged optimizers. [MLX-LM LoRA documentation](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md) provides the local adaptation basis; the installed APIs were inspected rather than upgraded.

[Yu et al., ICML 2026](https://proceedings.mlr.press/v306/yu26av.html) motivates separating outcome correctness from supported explanations. This run does not implement their CIR/SR metrics. [SFT Memorizes, RL Generalizes](https://proceedings.mlr.press/v267/chu25c.html) and [BRIDGE](https://proceedings.mlr.press/v306/chen26an.html) motivate held-out variants and possible future work; neither proves an OT benefit here. [DPO](https://arxiv.org/abs/2305.18290) is a future option, not an executed stage. No RL, DPO or Cloudflare fine-tuning is performed.

## Reproduction

Run from this isolated worktree. The following defines the exact existing interpreter and local snapshot, then the six individual stage commands. Use a new root for a newly authorized experiment; existing stage claims deliberately prevent reruns. Do not replay this locked test or revise its labels after results.

```sh
TRAIN_PY='/Users/xienanzheng/Desktop/Berkeley/School/Sem 3 MIMS/M3 Fellowship/water-ot-ai-lab/.venv-posttrain/bin/python'
MODEL='/Users/xienanzheng/.cache/huggingface/hub/models--mlx-community--Qwen3-4B-4bit/snapshots/4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25'
EXPERIMENT_ROOT='artifacts/typed-qwen-2026-10-31'
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage prepare --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage baseline --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage train --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage validate --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage test --root "$EXPERIMENT_ROOT" --model "$MODEL"
caffeinate -i "$TRAIN_PY" -m scripts.run_typed_training --stage report --root "$EXPERIMENT_ROOT" --model "$MODEL"
```

Actual baseline/train/validate/test/report stdout/stderr are saved in corresponding stage `.log` files. Every stage verifies Python/package versions, frozen records, model files and source hashes. Runtime source revision is `20a709fd780dab3f1a92bf925802544f6649d05b`; the recorded results belong to that evaluated revision. The subsequent reviewed runner repair changes hash-bound source and was tested only with CPU stubs; it does not change or revalidate the historical model results. `manifest.json` records individual hashes and settings. Training completion binds both checkpoint and adapter configuration hashes; selection binds validation results and chosen adapter files; test completion binds exact test result hashes. These checks detect drift, but are not externally signed attestations.

Historical report verification requires a separate checkout of `20a709fd780dab3f1a92bf925802544f6649d05b` with the retained artifacts available read-only. The repaired checkout correctly rejects the old manifest's source binding. Never rebind that manifest to repaired source, rerun training/locked test, or overwrite the existing `summary.json`/`failures.json`: report writes still use exclusive creation. Verify retained inputs with `verified_report_inputs` from the evaluated checkout, without invoking the report-writing stage on existing outputs.

The repaired reusable runner flushes an unavailable case row and aborts on `MemoryError` or a `RuntimeError` raised by the model/backend forward path (including MLX Metal resource-limit failures). It preserves exclusive stage claims, partial rows and a failure record with attempted/total/unattempted counts. No successful result, checkpoint selection or test completion is emitted for an aborted stage, and no subsequent case/model is run. Ordinary per-case validation/decoding errors remain recorded unavailable outputs. Load/warm-up failures already propagate and retain their claims. These guarantees were checked with CPU stubs only; none warrants replaying the frozen experiment.

## Proposed next experiments

First version a compact typed prompt that retains protection flags, source ages/quality, objective, current target, wait and coherent trend, while representing each menu label/reason/target once. Expand explanation templates after decoding. Verify information parity and measure matched latency; this would be an interface/prefill optimization, separate from any weight quality gain.

Compare against deterministic SOP logic and the existing controller; test new process packages and complete closed-loop episodes. Define sustained recovery, time/energy, excessive movement and unsupported-claim outcomes before considering RL. Hard protection must remain external. Admit teacher drafts only after independent policy and conversion checks into a newly frozen corpus. Calibrate auditor misses, false rejections and latency; an auditor pass is neither a teaching label nor execution authority. None of these proposals alters this run.

## Artifact identities

Selected adapter directory: `artifacts/typed-qwen-2026-10-31/checkpoint-128/` (relative to the isolated worktree). The original frozen checkpoint remains at `adapters/0000128_adapters.safetensors`. Both checkpoint candidates are preserved.

| Artifact | SHA256 |
|---|---|
| Model weights | `e240c0bdc0ebb0681bf0da0f98d9719fd6ebe269a3633f81542c13e81345651d` |
| Model file-map digest | `97963ad97f4a014d0c76afcfbae7a01d932a13a1d03a986c7012f53f0a83aa2a` |
| Source file-map digest | `8221ef357f4da86d0cc929f298aa98dc9c0b47fc29535fa15c9b33d39b948bca` |
| Experiment manifest | `2fc39d6f1a19a163e50fcd0d3bb9d847ca8eb20008bd91b863e9973b9753980f` |
| Dataset manifest | `42b0fa17f2d1fd1687c29c15c3c70d7d11af0c540652ca1947bc4f99dcb98fc4` |
| test.jsonl cases | `8106bb6369dbb8ea740e11aee202bccd7102f6a6ea903c31acd6afc47792749e` |
| train.jsonl cases | `70fd6f9cd3ab6a6ee7d0820de696ae577b630bed242b776e8efa0671d6752eab` |
| validation.jsonl cases | `741cbae95a00c85eb7c45a3b370ab1f898055393fb514f3ba8b7aba5772d912a` |
| test-frozen.json | `c2e4130693b6633e3f8f7b52c669a3b9ff24353d435bb58861da20ec0dd63f3a` |
| train-frozen.json | `0725f4756cdaa7ec215bc1aec57b3856ff07a9a5e6625ef2c7c6fcf3dee4a109` |
| validation-frozen.json | `456c40eb17c71e116aa632e6e4c8d1d4b01e053b605a1177ef22d2a8492fc161` |
| Selected adapter weights | `85e0b09a1beef383fcf3dea428eafacfe461b28202b2eabd382ca1221c9876cb` |
| Selected adapter config | `b0f9d5a4d9932df42ed5cae169a7e4fc94e768a32e25cbed7e08fc77f43fd8ca` |
| Selection | `a97396200efec7bd0f37df159ba823a474c56043813e5f5a07875e1f0565d121` |
| base-test.json | `a284bb9c70af6df6222d33ae3b4b3f81b8df2fc53dd19737e033e1e72e3ea3db` |
| selected-test.json | `466b77bafab6e214beadc37f0cb0b4a8b56e0c2aaeafae8349402350c87d8a22` |

File-map digests use SHA256 of sorted-key JSON (the experiment fingerprint function); individual model/source hashes remain in `manifest.json`. Source and full model bindings passed every stage through report generation. All artifacts stay ignored and private.
