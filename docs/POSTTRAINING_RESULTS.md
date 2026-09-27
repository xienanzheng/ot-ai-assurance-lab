# Local Qwen adapter pilot — 26 September 2026

**Decision: do not promote the adapter.** The pilot demonstrates a working local training/evaluation pipeline, but its critical-condition behavior is inadequate.

## Method

Qwen3 4B, four-bit MLX base, four trainable layers, 1.835 million trainable parameters (0.046%), batch size one, learning rate 0.00005, prompt-masked SFT, seed 42. Peak reported training memory was about 3.12 GB. The 120-step run processed 5,056 supervised tokens; this is a small curriculum pilot.

The curriculum contains explicit rules for simulated water-disinfection adjustments and holds. Labels come from code, not plant experts or successful recovery trajectories. Training/validation/test seeds are disjoint. After reviewing the first pilot, the longer run was evaluated on fresh seeds starting at 40002. Both evaluations also contain six critical-alarm overrides absent from training. These share templates with the curriculum and are not an independent operational benchmark.

## Recorded results

| Check | 24-step base | 24-step adapter | Fresh-case base | 120-step adapter |
| --- | ---: | ---: | ---: | ---: |
| Valid JSON | 18/18 | 18/18 | 18/18 | 18/18 |
| Correct actions and status | 0/12 | 4/12 | 0/12 | 8/12 |
| Critical-alarm overrides | 0/6 | 1/6 | 0/6 | 2/6 |
| Median generation seconds | 5.28 | 2.92 | 4.41 | 2.17 |

Correctness requires exact action targets/values and the expected continue/escalate status; syntactically valid JSON is not a correct decision. The lower latency partly reflects shorter outputs and caching. These small single-pass measurements do not establish a speedup for full plant prompts or the hosted Qwen model.

Training validation loss decreased from 3.216 to 0.081 in the longer run, but the poor critical-alarm result shows why lower loss is insufficient. The base model also performs poorly on these checks; that is a finding requiring broader evaluation, not evidence that this adapter is deployment-ready.

## Feedback validation

- Controlled provider responses passed through the real grid and nuclear gates: approved target visible in plant state, early repeat rejected, response interval observed, bounded lease released and baseline targets restored. Both Qwen and Jev adapter paths are covered.
- Concurrency, pause/reset behavior, in-flight cancellation, escalation preservation, contradictory escalation-plus-action rejection, sensor-contract names and bounded observation history have regression coverage.
- A live Jev healthy-grid run completed two decisions with the refreshed context and stopped at its budget. Both decisions held existing targets; measured API latencies were approximately 0.28 and 0.18 seconds. This validates connection and orchestration, not disturbance recovery.
- After training completed, a separate live local Qwen loop completed two hold decisions and stopped at its budget. Full-context inference took 40.089 and 36.135 seconds. Both real-provider trials exercised a healthy grid, not disturbance recovery. Water gate tests separately verified the 12-minute chlorine observation window and 14-minute adaptive lease.
- Running local Qwen inference concurrently with MLX training caused substantial contention (one recorded inference took 99 seconds). That run is excluded from normal latency comparisons. Stopping the loop prevented the late result from applying.

## Artifacts and next acceptance requirements

Local raw results: `artifacts/posttraining/sop-evaluation-24steps.json`, `sop-evaluation-120steps.json`, `live-feedback-jev.json`, `live-feedback-qwen-isolated.json`; adapter: `artifacts/posttraining/qwen-sop-pilot/`. They are ignored by Git. Source scripts are in `scripts/train_sop_adapter.py` and `scripts/evaluate_sop_adapter.py`.

Next training work should explicitly cover critical alarms, conflicting instructions, stale/missing measurements and multi-step delayed outcomes, with a locked independent evaluation set. Compare typed candidate selection against free-form target generation to separate decision selection from arithmetic errors. Require reliable escalation and no gate violations before testing any candidate in bounded closed-loop trials. No online RL, automatic visitor-data training or hosted Jev fine-tuning was performed.
