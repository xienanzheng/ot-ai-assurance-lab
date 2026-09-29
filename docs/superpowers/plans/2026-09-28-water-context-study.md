# Water context study and hosted capacity implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline.

**Goal:** Test context assistance and a fresh local QLoRA candidate without changing active models, gates, or published evidence.

**Architecture:** A research-only runner uses the existing water context, simulator-derived labels and scorer. New episode seeds and artifacts isolate this development experiment. Compare ordinary context, code-assisted context and a typed-choice interface; distinguish code-supplied evidence from model diagnosis. Cloudflare receives configurable, bounded session/AI allowances, with conservative defaults.

**Tech Stack:** Python, MLX-LM, Qwen3-4B 4-bit, Workers AI Qwen3-30B-A3B, Node tests, Wrangler.

**Spec:** User request of 28 September: continue local fine-tuning, investigate online methods and improve hosted simulation where useful.

## Global constraints

- Preserve v2 datasets/results, paper artifacts and active model selection.
- No visitor data, online RL, automatic promotion, or plant actuation in this study.
- Code-derived choices/evidence are attributed; no expected labels enter inference requests.
- Fresh development cases; a new locked acceptance study is required before availability. This pilot is not certification.
- At most 80 initial QLoRA updates, four trainable layers, rank eight, batch one, prompt masking, gradient checkpointing. Compare against the same pinned base and prompts.
- Bound hosted pilot to 32 shared cases × three interfaces, temperature zero and fixed output limit. Save errors, requests, usage and scores; no correctness retries.
- No assumption of a credit balance. Expose capacity settings with limits and retain current deployed defaults until configured.

## Tasks

1. [x] Add context/choice helper and fresh dataset preparation; test label independence, prerequisite/wait precedence and teacher consistency.
2. [x] Add resumable, provenance-bound local and hosted pilot runners; token preflight; run matched local baseline, 80-step SFT and adapter validation.
3. [x] Run bounded hosted three-interface pilot, preserving raw responses and full denominators.
4. [x] Add server-side capacity configuration with upper bounds; test session isolation, budgets and unchanged safety gate behavior; audit Cloudflare configuration and build.
5. [x] Record measured findings, remaining limitations and reproducible commands.

## Review focus

Identity/resume checks; no answer leakage; missing/stale/future instruments; no test reuse; no automatic model promotion; spend caps remain server-side; capacity metadata reflects actual allowances.

## Execution ledger

- Existing branch: `water-alarm-candidate`; no tracked changes at start. Untracked 25 September plan is pre-existing and untouched.
- Ruling: use an 80-update development pilot before investing in a larger sweep. The previous adapter's failure pattern warrants changing context and targets, not extending the old run.
- Ruling: retain the existing scorer for comparability. No new locked-test claims from this pilot.
- Task 1 complete: 1,200/160 balanced fresh development cases; maximum training sequence 2,308 tokens; no truncation. Five new study tests passed. Twelve saved v2 rows reproduce exactly after JSON normalization (tuple/list representation initially caused a comparison failure).
- Task 3 complete: hosted ordinary/assisted/typed decisions correct on 10/15/14 of 32 respectively. One authentication failure retained in baseline denominator; Wrangler refreshed OAuth before continuing. No promotion. Shared input schema's optional assessment was frequently omitted by generative variants.
- Task 4 complete: configurable positive-integer budgets with bounded ceilings; accurate global/session remaining allowance. Fourteen policy tests, four recorded-demo tests and five visitor tests passed. Sixty-seven focused Python tests passed. Worker/container dry-run passed. Local Worker smoke checks verified inactive session RPC, unauthenticated simulator rejection, cross-origin rejection and homepage response.
- Ruling: hosted pilot mirrors the deployed model transport's 2,048-token ceiling; local matched inference uses 256. Do not present these timings as a controlled local/cloud comparison.
- Ruling: prepare the six-session ceiling while retaining the original admission/spend defaults. No credit balance was verified and the request asked to check deployment improvements; nothing is published by this experiment.
- Ruling: after the new candidate evaluation, compare the preserved v2 adapter on the same 32 assisted prompts. This checks whether the new work actually improves on the earlier trained weights, rather than only an untrained base. Additional local inference only; no new training or hosted calls.
- First candidate complete: 80 updates, 32/32 valid, 16/32 correct, 8/8 critical, 8/8 prerequisite, 0/8 hold, 0/8 adjustment. It escalates every case and is not promoted. Reduced loss did not establish better useful decisions.
- Ruling: add one separate 80-update compact-choice SFT candidate under `typed-study/`. Supervise the semantic decision rather than a long repeated response template. Use the same fresh training/development splits and compare a matched compact base first. This is a second development strategy, not a new locked test or an expansion of inference authority. Maximum total new training: 160 updates across two candidates.
- Task 2 complete: both new candidates finished 80 updates and all 32-case evaluations. Both always escalated, scoring 16/32. Compact base scored 12/32; previous adapter under assisted context scored 15/32. Neither candidate is promoted.
- Task 5 complete: final audit verified all 256 records across eight variants, shared case IDs, cached scores, source bindings, training settings and base/adapter integrity. Final focused Python suite: 69 passed. JavaScript suite: 23 passed. Results, failures, confidence limitations, source references and commands recorded in `docs/WATER_CONTEXT_STUDY.md`.
- Final review: labels contain all four decisions; prompt masking preserves inference prefix; no label access in inference helpers; no changes to control gates or model selection. Both candidates equal the always-escalate baseline, so no usable control-policy improvement is claimed. Next study should test class balance/decision-focused loss rather than extending these runs.
- Hosting review: live catalogue confirms LoRA for Qwen2.5-Coder-32B, QwQ-32B and Llama 3.2 3B, but not current Qwen3-30B FP8. A supported-base upload compatibility experiment remains future work. Credit lookup returned 403; no usage-cap increase or deployment was made.
