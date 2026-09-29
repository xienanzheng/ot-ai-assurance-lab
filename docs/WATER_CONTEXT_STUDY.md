# Water context and QLoRA development pilot

28 September 2026. **Completed: two 80-update local candidates and eight 32-case comparison variants. Neither candidate is approved.** Research-only; no active-model replacement or automatic actuation.

## Design

The previous 4B adapter failed its locked test. Extending that run on its inspected test cases would not provide fresh acceptance evidence. This experiment creates 1,200 training and 160 development cases with new episode seeds, balanced between critical conditions, prerequisite failures, legitimate holds and justified corrections. It retains the same scenario families, so it measures development progress rather than generalization to unseen fault families. It does not open a new locked test.

The original context preserves alarms, sensor values/age/quality, trips, observation timing, previous readings, SOP text and untrusted retrieved notes. The assisted version adds code-derived residual error, remaining observation time and four candidate bundles. The bundles contain bounded target arithmetic and SOP evidence references. They are possibilities, not preapproved actions. Expected answers are used for training and scoring only; the inference helper accepts a payload without labels.

All full training sequences fit within 2,308 tokens. No sensor evidence is truncated. The local experiment compares the same pinned Qwen3-4B 4-bit base, assisted prompts and decoding settings before and after 80 updates. Training uses MLX QLoRA, four trainable layers, rank eight, learning rate `5e-5`, batch one, prompt-masked loss and gradient checkpointing. It starts from the pinned base, not the failed adapter. This isolates the new curriculum/context from continuation of old weights.

The hosted pilot uses Qwen3-30B-A3B FP8 with ordinary context, assisted context and a typed choice. Each receives the same 32 cases (eight per category). Transport mirrors the production Worker: schema-constrained JSON, temperature zero, seed 42, 2,048-token ceiling. The water-study decision contract is narrower than the live application contract; this is not a full live-loop acceptance test. The typed interface has code-populated actions and references, so its supported-assessment metric is not independent model diagnosis.

Local inference uses a 256-token ceiling and the MLX non-thinking template. Hosted and local timings are not a controlled speed comparison. Local matched timings are sequential and exclude the first cold sample. Other desktop activity was not controlled; this small pilot is not a hardware benchmark.

## Hosted findings

| Interface | Critical | Prerequisite | Hold | Adjustment | Total correct | Valid | Supported assessment |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ordinary context | 5/8 | 0/8 | 5/8 | 0/8 | 10/32 | 28/32 | 0/32 |
| Assisted context | 6/8 | 0/8 | 8/8 | 1/8 | 15/32 | 32/32 | 0/32 |
| Typed choice | 6/8 | 0/8 | 8/8 | 0/8 | 14/32 | 32/32 | 18/32 |

The first ordinary-context request failed authentication before inference. Wrangler refreshed the login and collection resumed by case ID. That failure remains in the 32-case denominator; it was not silently replaced. There were 31 successful ordinary-context responses and 32 for each other interface. The ordinary-context responses included two fabricated references. No correctness-based retry or plant command was issued.

Reported hosted usage totals: 219,589 input tokens and 5,520 output tokens. At the currently documented model rates, this is about $0.013 of inference before allowances; it is an estimate from token usage, not an invoice or a credit-balance measurement. [Model pricing](https://developers.cloudflare.com/workers-ai/models/qwen3-30b-a3b-fp8/)

Assistance improved this small pilot's decision rate but did not solve prerequisite handling. Schema-valid JSON was frequently incomplete as evidence: the generative responses often omitted the optional alarm assessment. Choice generation removed fabricated identifiers, but it did not make the selected decision correct. None of these variants qualifies for deployment. Missing assessments and prerequisite recognition need explicit attention in the next separately versioned contract experiment.

Representative saved failures (full IDs share `water-context-v3-pilot:valid:episode-`):

| Episode | Variant | Observed error |
|---|---|---|
| `1200030` | Local base with assistance | `CLEARWELL_OVERFLOW`: returned `escalate` but also proposed a chlorine target change. |
| `1200133` | Hosted assisted | Missing chemical flow proof: returned `continue` and claimed flow was within limits. |
| `1200084` | Hosted typed | A justified decrease was selected as an increase. |

These are proposed decisions from offline evaluations. They were not executed by the simulator. The full inputs, outputs and expected mappings are retained in `representative-failures.json` and the per-variant records.

## Local findings

The first matched local run is complete:

| Assisted generative interface | Critical | Prerequisite | Hold | Adjustment | Total correct | Valid |
|---|---:|---:|---:|---:|---:|---:|
| Pinned base | 2/8 | 5/8 | 0/8 | 0/8 | 7/32 | 25/32 |
| Previous v2 adapter, same assisted context | 6/8 | 1/8 | 8/8 | 0/8 | 15/32 | 32/32 |
| New 80-update adapter | 8/8 | 8/8 | 0/8 | 0/8 | 16/32 | 32/32 |

The new adapter escalated **every case**. It improved escalation and formatting but failed both useful noncritical categories, so it is not a successful control-policy improvement. Supported assessments increased from 18/32 to 24/32. The adapter had no fabricated references. Warm median/p95 changed from 10.28/13.12 seconds to 7.68/8.38 seconds under matched local prompts/settings. The four-example validation loss fell from 1.698 to 0.029; this did not predict correct hold/adjust behavior.

A second, separately recorded strategy uses compact-choice supervision: `decision` plus confidence, with actions/references expanded by code. The hypothesis is that this puts more loss on the semantic choice instead of repeated JSON fields. Its training targets are derived from the reviewed scenario mappings; inference still receives no labels. It uses the same 1,200/160 development splits and the same 80-update settings, with a matched compact base evaluated first. Maximum full training sequence is 2,100 tokens. This is not independent model-generated diagnosis, and it does not change any active model. A comparison of the preserved v2 adapter on the same assisted pilot is also recorded.

The previous adapter's 15/32 here is a new development comparison with assisted prompts, not a replacement for its original 400-case or locked-test results. All training confidence targets are fixed at 0.8; these experiments do not calibrate uncertainty. Emitted confidence must not be interpreted as an empirical probability of a safe or correct decision.

The compact run also completed and was audited:

| Compact interface | Critical | Prerequisite | Hold | Adjustment | Total correct | Valid |
|---|---:|---:|---:|---:|---:|---:|
| Pinned base | 4/8 | 0/8 | 8/8 | 0/8 | 12/32 | 32/32 |
| New compact 80-update adapter | 8/8 | 8/8 | 0/8 | 0/8 | 16/32 | 32/32 |

The compact adapter also selected escalation for every case. Its 24/32 supported assessments reflect code-derived evidence expansion, not independent diagnosis. Matched warm median/p95 changed from 6.49/7.26 seconds to 6.20/6.42 seconds. Four-example validation loss fell from 3.016 to 0.060, but useful hold/adjust behavior did not improve.

Both new adapters match the **16/32 always-escalate baseline**. They are not successful overall control-policy improvements, despite higher escalation/formatting scores than their bases. There is no evidence here supporting promotion or a claim that continued SFT made the model operationally better.

The data check confirmed all four choice labels are present: 600 escalation, 300 hold, 150 increase and 150 decrease training targets; validation has 80/40/20/20. Prompt-masked training prefixes match inference. The examples are balanced by scenario category, but not by decision class. A hypothesis for the next experiment is that frequent escalation and repeated output syntax dominate the learning objective. This is not a proven root cause. A more focused follow-up would use equal-token decision labels, class-balanced sampling or decision-token-weighted loss, and a separate development version. Keep both false escalation and missed escalation visible. Do not select or train on the old locked test, and do not simply extend either failed adapter's run.

See `local-run.log`, `previous-run.log`, `typed-run.log` and `audited-report.json` under the ignored experiment directory. All 256 comparison records across eight variants were recomputed and checked against the shared 32 IDs. No new locked-test or deployment claim follows from this pilot.

## Reproduce and inspect

```sh
.venv-posttrain/bin/python scripts/run_water_context_study.py prepare
.venv-posttrain/bin/python -u scripts/run_water_context_study.py local-study
.venv-interpret/bin/python -u scripts/run_water_context_study.py cloud-study
.venv-posttrain/bin/python -u scripts/compare_previous_water_adapter.py
.venv-posttrain/bin/python -u scripts/run_typed_water_adapter.py study
.venv-interpret/bin/python scripts/audit_water_context_study.py
```

The ignored artifact directory is `artifacts/posttraining/water-context-v3-pilot/`. It contains frozen cases, prompt-matched training chats, source/dataset hashes, selected pilot IDs, requests, raw responses, decoded proposals, scores, provider usage, transport errors, training command and adapter weights. Resume validates identities and recomputes cached scores. Changed source/data requires a new experiment version. Partial adapters are not overwritten. No run writes an approval or registers a model with the simulator.

The final audit requires complete, identical case-ID sets; compares captured prompts with the specified interface; recomputes scores/summaries; checks source bindings, training settings and adapter hashes; and checks the pinned base's files against previously recorded hashes. That last base-file check is an additional after-run integrity check, not a claim of new pre-run file hashing. Eighty batch-one updates per candidate are an initial pilot, not a full pass through all 1,200 available training examples.

The existing v2 benchmark generator gained optional seed/count arguments; its default behavior is preserved. Twelve saved v2 validation cases were regenerated and compared after JSON normalization. Historical source identities intentionally remain unchanged in the original artifacts; rerunning the old study against changed source is expected to fail its provenance check.

## Methods and hosting decision

Use context assistance and supervised QLoRA first. Consider rank-stabilized LoRA or a different adapter rank only in a matched follow-up that holds the data and interface constant. Preference training such as DPO would need reviewed chosen/rejected pairs, including cases where a superficially plausible adjustment is inappropriate. The current rule-labelled examples and API outputs do not automatically provide reliable preference labels. No visitor-data training or online RL is enabled. [PEFT LoRA documentation](https://huggingface.co/docs/peft/developer_guides/lora), [TRL DPO documentation](https://huggingface.co/docs/trl/dpo_trainer)

A custom 4B adapter cannot be applied to 30B. Training 30B would require its own compatible base and training environment. Cloudflare's current native LoRA guide lists selected nonquantized bases and configuration types `mistral`, `gemma` and `llama`; it does not establish upload support for this Qwen30B FP8 model. No Qwen adapter upload was attempted. A separately hosted GPU endpoint could later serve a trained 30B behind the Cloudflare application. [Cloudflare LoRA guide](https://developers.cloudflare.com/workers-ai/features/fine-tunes/loras/)

The live catalogue and individual model pages provide a more useful alternative than a blanket conclusion that Qwen adapters are unsupported:

| Base | Native LoRA advertised | Consequence |
|---|---|---|
| Current Qwen3-30B-A3B FP8 | No LoRA property in the returned catalogue entry | No verified upload path for our current hosted model. |
| Qwen2.5-Coder-32B-Instruct | Yes | Candidate for a separately trained Qwen adapter and compatibility probe. |
| QwQ-32B | Yes | Another supported Qwen-family base; latency and interface would need evaluation. |
| Llama 3.2 3B Instruct | Yes | Smaller candidate for a local-training/native-hosting experiment. |

If native Workers AI adapter hosting is the priority, start a compatibility experiment with a base that explicitly advertises LoRA. Reuse the reviewed curriculum, not Qwen4B weights. Confirm the exact base, adapter format and rank by serving a test adapter before committing to a long training run. The generic upload guide and model-specific Qwen listings are not fully aligned, so the upload configuration still needs an end-to-end probe. No supported-base adapter has been trained or uploaded in this task. [Qwen2.5-Coder-32B](https://developers.cloudflare.com/workers-ai/models/qwen2.5-coder-32b-instruct/), [QwQ-32B](https://developers.cloudflare.com/workers-ai/models/qwq-32b/), [Llama 3.2 3B](https://developers.cloudflare.com/workers-ai/models/llama-3.2-3b-instruct/)

The hosted application's admission/AI budgets are now configurable and bounded, with unchanged default allowances. The remaining-call display accounts for both session and shared daily budgets. The code supports a measured move from three to six concurrent sessions, but neither that increase nor a model change is published by this experiment. See [hosted capacity configuration](HOSTED_SIMULATOR.md#capacity-configuration-28-september).

Read-only account checks confirmed inference access. The live model catalogue lists the Qwen30B model with function-calling/reasoning/batch properties and no LoRA property. The billing-credit endpoint returned HTTP 403 with the current credentials, so the available credit balance could not be verified. No billing plan was changed.

## Software verification

- 69 focused Python tests passed, including the new context/target/audit checks and existing critical-transition, timing, candidate-isolation and operator-response tests. One existing Starlette deprecation warning remains.
- 23 JavaScript tests passed across hosted policy, recorded-demo routing and visitor handling.
- Wrangler dry-run compiled the Worker and built the container successfully.
- Local Worker smoke checks passed for homepage serving, inactive-session RPC, unauthenticated simulator rejection and cross-origin admission rejection. The temporary development server was stopped afterward.
- The final evidence audit passed, and `git diff --check` reported no whitespace errors. No inference proposal from these experiments reached plant actuation.
