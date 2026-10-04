# Jev teacher-response review — 27 September 2026

Qwen's version-2 experiment was paused for this review, preserving 112 baseline validation responses. It has now resumed on the user's explicit instruction. All 44 matching cases were rechecked and are already in the training set; no duplicate samples or Jev confidence labels were added. Neither model has been promoted; hosted configuration is unchanged.

## What was collected

Two sequential API passes used the same 48 **training-only** simulated water cases: 24 critical, eight prerequisite failures, eight holds and eight adjustments. No validation or locked-test cases were sent to Jev. The API resolved `typesafe/jev-1.13` to `typesafe/jev-1.13-20260917`.

Jev returns typed choices and probabilities, not a written rationale or a reasoning trace. The [official API explanation](https://openrouter.ai/blog/insights/what-is-jev/) describes this distinction. Candidate numerical targets, SOP evidence lookups and conversion to the Qwen JSON contract are application code.

## Results

| Scenario | First pass: correct action/status | Second pass: full rule match |
| --- | ---: | ---: |
| Critical | 24 / 24 | 24 / 24 |
| Prerequisite failure | 4 / 8 | 5 / 8 |
| Hold | 8 / 8 | 8 / 8 |
| Adjustment | 4 / 8 | 7 / 8 |

The first pass asked separate questions for disposition, control, alarm, sensor and operator check. Although its critical dispositions were correct, **zero responses passed every check together**: evidence mismatches and inconsistent separately selected decisions prevented use as complete teaching examples.

The second pass supplied explicit SOP mappings and asked for **one complete decision choice**. Code supplied each option's controls and evidence; Jev selected the option. **44/48** selections matched the scenario rules. This demonstrates a better result for the combined code-and-model design on these development examples, not improved independent model diagnosis or held-out generalization. The two passes changed both the supplied context and the choice structure, so their individual effects are not isolated.

Mean measured request latency was 0.199 seconds in pass one and 0.154 seconds in pass two. API-reported costs were $0.00709527 and $0.008351406 respectively (about $0.01545 total). These typed API calls are not a matched latency comparison with local generative Qwen.

## Failures retained

The second pass chose `hold` rather than escalation for:

- `episode-100809`: residual reading 317 seconds old.
- `episode-100812`: residual reading missing.
- `episode-100815`: residual timestamp 82 seconds in the future.

It also chose `hold` in `episode-100808`, where the scenario's SOP permits a small downward disinfection-target correction. No failed case proposed critical-state actuation, but failure to escalate remains a meaningful error.

These examples reinforce keeping measurement validity and protection checks in deterministic code. High confidence or a fast response must not substitute for those checks.

## Package for the next Qwen run

Local ignored artifacts:

- `artifacts/posttraining/jev-water-review-v1/responses.jsonl`: all first-pass requests, raw outputs and scores.
- `artifacts/posttraining/jev-water-review-v2/responses.jsonl`: all second-pass requests, raw outputs and scores.
- `artifacts/posttraining/jev-water-review-v2/qwen-review-examples.jsonl`: **44 review candidates**, with deployment-shaped messages and JSON targets.
- `artifacts/posttraining/jev-water-review-v2/failure-cases.jsonl`: the four excluded second-pass failures.

The 44 targets preserve the distinction between Jev's selection, code-defined controls/evidence, and the existing rule-labelled rationale. They are **not automatically approved training data**. The package does not change the frozen benchmark, active Qwen, gate, or hosted system. It contains simulated plant context, not visitor records; credentials are not exported.

Before further training, review the targets and provider permissions for distillation, retain a balanced curriculum rather than learning only escalation, and introduce hard negatives for timestamp and missing-data failures. Any changed prompt or training curriculum needs a new version and fresh matched baseline. The locked test stays untouched, and Qwen resumes only on explicit instruction (now received).

## Reproduce extraction

```sh
.venv-interpret/bin/python scripts/collect_jev_water_teacher.py
.venv-interpret/bin/python scripts/collect_jev_water_bundles.py
.venv-interpret/bin/python scripts/prepare_jev_water_review.py
```

Collectors use the existing local `OPENROUTER_API_KEY`, resume saved case IDs without duplicate calls, and reject changed extraction identities. Each pass is limited to 48 cases. They have no plant-control calls and do not start Qwen training.
