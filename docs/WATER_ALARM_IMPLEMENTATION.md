# Water alarm candidate implementation ledger

Approved scope: water-only critical escalation and evidence-based diagnosis. The active Qwen model and Cloudflare are unchanged. A candidate may be exposed only for local shadow comparison after all locked-test acceptance checks pass.

## Work items

- [x] Add shared training/inference water alarm context and grounded diagnosis contract.
- [x] Generate 2,000 training / 400 validation / 1,000 locked cases, with 500 critical test cases and versioned provenance.
- [ ] Run matched prompt-only baseline, two QLoRA candidates and validation-only selection.
- [ ] Run locked test and sequential matched latency benchmark; record acceptance decision.
- [x] Add approval-bound local MLX launcher and permanently non-applicable shadow comparison.
- [ ] Complete water episode, API, UI and regression checks; publish results.

## Decisions

- Train 160 updates per candidate (below the approved 400-update ceiling), four layers, rank eight, batch one, gradient checkpointing. Learning rates are 5e-5 and 1e-4. No further tuning after locked test access.
- Use batched generation for correctness scoring; use a separate sequential 32-case full-context run for latency, excluding its first cold sample. No training overlaps inference.
- Cases are explicit counterfactual fault/quality variants of actual simulator snapshots, not expert-certified plant trajectories. Episode-level holdout uses unique seeds and reserves compound faults, unfamiliar critical codes and misleading healthy readings for test. Separate episode tests exercise actual controller transitions.
- Candidate comparison uses the same captured state for current Ollama Qwen and the MLX adapter. Only offline base/adapter measurements use an identical inference backend and prompt; the UI comparison labels that difference.
- Preserve the user's pre-existing untracked structured-decisions plan.

## Review fixes and continuation, 27 September 2026

- Final: fixed cache identity reuse — changed-identity and legacy-artifact tests RED→GREEN. Evaluation binds base files, adapter/config, data and code before measurement and rejects mismatches.
- Final: fixed serving identity — unrelated-server/model-path/context-budget tests RED→GREEN. A fixed-model loopback wrapper identifies loaded weights and rejects path overrides.
- Final: fixed masked fabricated-reference errors — malformed-confidence plus invented-alarm test RED→GREEN; grounding is measured independently.
- Final: fixed independent protection coverage — benchmark coverage test RED→GREEN, adding isolated emergency/override/critical-state and future-dated evidence.
- Future-timestamp water-gate test RED→GREEN; corrected the shared safe fixture's accidental wall-clock timestamps to use simulation time.
- Ruling: preserve and terminate the incomplete v1 study; start v2 with matched non-thinking training/inference templates and expanded coverage. Version 1 never opened its locked test. Its partial results cannot be certified retroactively. Cost: repeat baseline/training time; no quality claim from the partial run.
- Ruling: v2 is a new experiment with at most two candidates, 160 updates each. Preserve the v1 adapter as a historical, nonqualifying artifact; never expose it through the candidate launcher. Cost: extra local compute compared with repairing only the old report.
- Ruling: context now retains actual controller keys (backwash sequence, equipment runtime, sensor selection and control source). Cost: a slightly larger prompt, still below the measured budget.
- Current verification: 223 Python tests passed / 3 integration skips; 13 JavaScript tests passed; frontend build passed. Browser fixture checks passed for availability, escalation/evidence and disabled shadow application. No real candidate service is approved yet.
- Current execution: corrected v2 study launched; output log `/tmp/water-alarm-study-v2.log`. Do not run concurrent local inference while measuring.
- Documentation: `docs/WATER_ALARM_EVALUATION.md` contains the retained failure case, current limitations, dataset hashes, dependency versions and reproduction commands.

## User-directed pause and Jev review

- Stopped Qwen study parent and inference child at the user’s request; preserved 112 baseline validation responses. No Qwen run was resumed by the later “continue” request.
- Collected two bounded 48-case Jev passes on training cases only. Second pass selects a single code-defined SOP bundle: 44/48 rule matches; 24/24 critical escalations. Evidence references are code-derived, not model-generated diagnosis.
- Exported 44 review candidates and four failure cases. No teacher data incorporated into the frozen Qwen study, no active model changes, no hosted changes. See `JEV_WATER_TEACHER_REVIEW.md`.

## Explicit resume after Jev review

- User authorized “resume Qwen now, and now train it and test it”. Rechecked all 44 Jev review examples against the original training prompts and scenario labels; all pass. All already occur in the 2,000-case curriculum, so no duplicates or model-confidence targets were introduced.
- Verified evaluation identity before resume; retained 112 completed baseline validation rows. Locked-test model outputs remain absent. Preserved the pause metadata and recorded explicit resume metadata locally.
- Resumed the existing sequential study at 160 updates for each of two candidates. Validation-only selection precedes the locked test and sequential latency comparison. Passing enables only local shadow availability.
