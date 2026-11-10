# V2 decision and audit improvements — 25 October 2026

## Problem and scope

The local scenario run found three different defects: incorrect Qwen decisions, malformed evidence references, and unreliable Gemma reviews. These are not interchangeable. A clean JSON response is not a useful control decision; a model audit pass is not an independent safety guarantee.

This iteration changes the standalone V2 water/cooling interface and deterministic validation. It does not train weights, install the previous Qwen adapter, change V1, or deploy to Cloudflare. It uses the existing base Ollama Qwen3:4b and Gemma3:4b.

## Implementation and attribution

1. **Ground reference IDs.** JSON schema enums restrict sensor/check references to the captured package. Runtime validation rejects unknown references even if a provider disregards the schema. Historical records remain readable.
2. **Represent actual settling.** Calculate trend only from ordered, good-quality observations with the same target, generation and package. Export value change, elapsed process time and progress toward the objective. A falling value is insufficient if the current target itself remains above the objective.
3. **Clarify SOP precedence.** Contrast protection, active waiting, in-band operation, demonstrated settling and bounded correction. Illustrative examples do not contain benchmark labels or replace the model's target selection.
4. **Separate model opinion from factual checks.** The selected Gemma contract emits only passed/flagged and a concise reason. Single-issue-category variants were tested and rejected after they scored 8/16. The model was confusing fault classification with proposal review. Deterministic SOP/reference/bounds checks may veto a model pass. The export preserves the raw model verdict, separate findings and source of the effective result. A code-vetoed false pass is not credited as improved model reasoning.
5. **Reject worsening commands.** For the installed direct-target benches, the controller gate rejects unchanged/wrong-direction targets when the measured value is outside the objective. This applies with audit off as well. It is not a general rule for raw actuators whose process gain might be negative.
6. **Allow one bounded correction.** A factual conflict is returned to Qwen once, on the same captured inputs. Preserve both requests/replies, findings and timing. A failed second attempt is retained; there is no unlimited retry or scripted replacement action. The supervisor keeps its existing 50-second analysis deadline, and controller freshness checks still apply. One supervisory decision can now contain two model requests.
7. **Plan finite-time response.** A live run exposed a target exactly at the objective boundary: it was valid and applied, but approached the band without entering it. A subsequent candidate exposes the objective midpoint, its projection into the permitted step, and a nominal first-order response time. Settling holds require an interior target. A boundary target is allowed as a necessary intermediate step when the interior is not reachable yet. These are explicitly server-calculated planning aids, not learned model knowledge.
8. **Keep generation concise.** New decision rationales are capped at 300 characters; historical records retain their prior schema. This limits output size without discarding the captured measurements or hiding the original/revised proposals.
9. **Preserve failure evidence.** Invalid audit replies retain raw content, elapsed time and error detail; cards get a short explanation. Unavailable audits never become approval.

Audit off/observe/required semantics and controller protection remain distinct. These improvements neither silently replace a Qwen proposal with a rule-based command nor authorize critical-state control.

## Evaluation plan

Preserve original results. Replay the existing 16 development decision cases and 16 audit cases sequentially, one response per case, with exact requests/outputs and source/model hashes. Score direction/status, structure, IDs and evidence separately. Report effective audit results separately from raw Gemma results. Development compared the single-pass interface and a one-correction candidate; neither used confirmation outputs. The bounded candidate was selected at 15/16 correct status/target decisions. Only after development candidate selection, run the previously reserved 12 confirmation decision cases; do not tune on their outputs. Repeat representative live actuation/monitoring only after software checks pass. Any expanded or revised candidate gets a new artifact name rather than overwriting evidence.

## Angles that need more work

- **More context is not always the answer:** the failed replies already contained the relevant facts. Additional unstructured SOP prose can reinforce the wrong interpretation. Separate precise prerequisites, arithmetic and process goals from narrative documentation.
- **Controllability and disturbance:** target direction alone does not establish reachability. A sustained external disturbance can defeat an apparently sensible target. Evaluate saturation, exhausted headroom, stalled recovery, model-versus-observed residuals and time-to-recovery, rather than rewarding repeated adjustments or endless settling holds. The new nominal forecast assumes no added disturbance; it does not solve disturbance estimation.
- **Time and data provenance:** a sensor can be fresh but stuck, or disagree with a redundant sensor. Add plausibility/residual checks and a validated process model before relying on statistical relationships. Separate observation windows from communication latency and actuator acknowledgement.
- **Modular control direction:** new packages need explicit capability semantics, gain direction, actuator limits and coupling constraints. Do not reuse a cooling setpoint rule for a valve opening percentage without qualification.
- **Anticipation versus reactive control:** define when an in-band measurement with a drifting or out-of-band target warrants preventive adjustment, and when demonstrated settling forbids another change. Keep accepted command history distinct from untrusted prior model suggestions.
- **Helpful versus safe:** always holding/escalating can appear safe while accomplishing nothing. Keep separate metrics for justified action, unnecessary escalation, missed escalation, recovery, overshoot and command count.
- **Auditor calibration:** test known good controls alongside malicious or mistaken proposals. Include healthy-looking readings with trips, misleading rationales, invalid IDs, unit changes and prompt injection. Different model families alone do not establish independence.
- **Learning:** collect reviewed state → decision → observed-outcome episodes. Use balanced supervised adapter training first; consider preference training only after reward/scorer calibration. Do not train from Gemma passes or unreviewed visitor interactions. RL against a flawed reward can amplify excessive holds or exploit simulator shortcuts.
- **Qualification:** use episode-separated scenarios, unseen disturbances and parameter variations, followed by real-time hardware-in-the-loop work. Better bench performance is not evidence of readiness for a real plant.

## Recommended next experiments, in order

1. **Resolve the action policy before more training.** Specify preventive adjustment versus in-band hold, and measurable stagnation versus legitimate settling. Freeze new episodes before evaluating a revised policy. Report unnecessary actions as well as rejected useful actions.
2. **Measure the process-model mismatch.** Add parameter sweeps, disturbances, sensor bias/stuck values and actuator mismatch. Compare forecast versus observed response, time in range and overshoot. A setpoint acknowledgment is not proof of achieved flow or dose.
3. **Calibrate or replace the reviewer.** Evaluate another locally runnable model on a newly frozen balanced proposal set. Score false passes, false flags and whether the stated reason is supported. Keep deterministic checks independent and distinguish advisory observation from a required audit.
4. **Train from reviewed outcomes.** Build episode-separated SFT examples from both successes and failures, with explicit operator-review labels. Evaluate against the frozen base interface. Do not use model-auditor passes as ground truth or claim that interface changes are weight training.
5. **Qualify a physical connector separately.** Verify tag identity, units, permissions, command acknowledgement, restart/replay handling and independent plant interlocks on a simple isolated PLC bench. The current tests operate only on the local simulated controller.

## Source notes

- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs): schema-constrained generation plus runtime validation. Semantic correctness still needs independent checks.
- [Building effective agents](https://www.anthropic.com/research/building-effective-agents): explicit workflows and programmatic checks before adding agent complexity.
- [Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685): documented judge biases and reasoning limitations motivate separate factual checks and calibration. This paper does not validate this OT implementation.

## Recorded evaluation stages

| Qwen decision interface | Correct status/target | Valid references | Observed median |
|---|---:|---:|---:|
| Previous focused interface, same development cases | 8/16 | 14/16 | 3.60 s |
| Revised single-pass interface | 13/16 | 16/16 | 4.35 s |
| One bounded correction | 15/16 | 16/16 | 4.62 s |
| Bounded candidate, reserved confirmation cases | 12/12 | 12/12 | 4.64 s |

Low cooling still escalated unnecessarily in the development set. Correct targets do not establish correct explanations: some rationales confused headroom or used unsupported arithmetic. Timing is an observed sequential replay measure, not a controlled speed claim. Difficult correction cases took about 19–23 seconds; the first live water decision took 28.8 seconds with a lengthy rationale.

| Auditor interface | Raw model correct | Combined correct | Raw / combined false passes |
|---|---:|---:|---:|
| Earlier focused review | 12/16 | 12/16 | 0 / 0 on its calibration set |
| Single issue category | 8/16 | 8/16 | 0 / 0 |
| Issue category + explicit proposal arithmetic | 8/16 | 8/16 | 0 / 0 |
| Binary verdict + arithmetic, development | 12/16 | 12/16 | 0 / 0 |
| Binary verdict, fresh confirmation probes | 9/16 | 10/16 | 1 / 0 |
| V4 binary verdict, reused development probes | 12/16 | 12/16 | 0 / 0 |

The fresh audit set was balanced between eight correct proposals and eight bad ones. The deterministic reference check caught Gemma's false pass on an invented water sensor. Six legitimate responses were still rejected by the combined review. There is **no demonstrated improvement in Gemma's underlying judgement**. It remains optional; required mode can still reject useful actions. The changed contract eliminates the observed contradictory-category format failure, not semantic errors.

### Live boundary discovery

The bounded candidate applied Qwen's own water target of **1.1 mg/L** and made two scheduled follow-ups. Four of six live checks passed, but measured residual remained above the objective and sustained recovery failed. This is preserved in `artifacts/model-review-v2/live-water.json`, not relabelled as success. The final response-planning candidate was developed from that failure, so the earlier 12-case confirmation is no longer independent evidence for the later candidate.

The accompanying critical-transition trial passed 8/8 checks and, unlike the earlier hold-only trial, rejected a genuine late Qwen adjustment after protection activated.

### Response planning and typed recovery constraints

The V3 response-planning candidate achieved **20/24 correct decisions**, with valid structure and references in 24/24. Only **4/8** adjustment cases selected targets projected to recover within the nominal episode. Extra explanatory context alone did not solve target selection. The original cooling live run did recover with Qwen's 11°C target: 124 seconds from acceptance through sustained recovery, with six checks passing. This contrasts with the failed water boundary target; both results are preserved.

V4 changes the interface: the server offers a small menu of targets inside existing absolute, per-step and cumulative limits. Where an initial interior recovery target is reachable, the interval excludes 10% of the objective width at each edge. The model chooses a target from that menu or chooses hold/escalate. The independent controller also checks the recovery interval. If the interior cannot be reached in one step, a correctly directed intermediate step remains possible. If the current target is already strictly inside the objective, bounded compensation outside the objective remains available for unmodelled disturbances. An existing disturbance test caught an overly restrictive first version of this rule; it was fixed without weakening that test.

This margin is a local bench engineering policy, not a site-approved operating procedure. Candidate target generation is **code-derived assistance**, not learned control expertise. Neither it nor the nominal first-order projection proves physical recovery.

| Replay | Correct status/target | Valid structure / references | Nominal recovery targets in adjustment cases | Median |
|---|---:|---:|---:|---:|
| V3, fresh 24 probes | 20/24 | 24/24 | 4/8 | 4.62 s |
| V4, same 24 probes (regression) | 21/24 | 24/24 | 8/8 | 5.06 s |
| V4, original 12 confirmation cases (now regression) | 12/12 | 12/12 | 0/2 | 4.75 s |

The two adjustment cases in the original 12-case set require intermediate bounded steps; a single step does not provide full nominal recovery. Do not interpret 12/12 decision correctness as 12/12 recovered episodes.

V4 still adjusted two already-in-band observations and interrupted one valid settling period. The in-band examples had out-of-band targets, exposing an unresolved policy question: reactive SOP compliance versus anticipatory correction. The frozen labels were retained; these are counted as failures rather than relabelled after seeing the outputs. Other rationales still contain inaccurate descriptions. Numeric controls and model explanations are therefore displayed separately.

The 24 cases informed V4, and the earlier confirmation set has now been reused. These are regression results, **not new held-out generalization evidence**. A future training or release claim needs a newly frozen evaluation set. No model weights were changed.

### Final live verification

The final water trial used Qwen's own **1.025 mg/L** proposal, accepted by the controller. It entered the 0.95–1.10 mg/L objective after **90.7 seconds** and achieved the 30-second sustained-recovery criterion after **120.9 seconds** from acceptance, at real 1× process time. Two scheduled Qwen follow-ups both held the target. All seven live checks passed, including completion of background reviews. This was not a fixture command.

Gemma falsely flagged the initial valid adjustment, then passed both valid holds. Its initial explanation confused the proposed interior target with the captured starting state. Advisory mode recorded that flag without changing actuation; required-audit mode would have blocked the command. The model flag was not silently overruled or represented as a pass.

The final critical-transition trial passed **8/8** checks. The late Qwen response proposed an actual adjustment to 1.025 mg/L. Current critical protection and the changed supervision epoch blocked it, disarmed control and stopped further feedback. This proves the tested late-command rejection path, not universal critical-state safety.

The first V4 cooling run applied **11.2°C** and recovered in **159.8 seconds**, but it exposed a scheduler defect. Starting monitoring immediately after acknowledgment could reuse the last pre-command OPC UA sample. That spent one call on a duplicate adjustment; the controller blocked it during the observation window. The six original live checks passed, but they did not check the follow-up's captured process time. This run is therefore **not accepted as a clean monitoring success**.

The fix derives the observation deadline from validated command acknowledgments as well as telemetry, scoped to the same package and generation. It does not fabricate newer sensor values or relax waiting. A regression test reproduced the early call before the fix; a second test ensures an old episode cannot delay a new episode. The live checker now explicitly verifies that follow-ups were captured after the accepted command's wait. The revised software suite passes **96 tests**.

The cooling rerun with the scheduler fix passed **7/7** checks. Qwen selected **11.2°C**; measured temperature achieved sustained recovery after **160.6 seconds** from command acceptance. Both follow-ups occurred after the acknowledged observation deadline and returned holds, with no duplicate command rejection. These are measured real-time simulated outcomes, not the nominal projections used in the replay table.

The second cooling hold still described the measurement as above the objective when it was already inside. Its disposition was correct, but its explanation was inaccurate. Correct JSON, valid references and correct action/status must not be reported as fully supported reasoning.

The final local bench was restored to **water, audit off, feedback stopped and controller disarmed**. The browser rendered the updated numeric command cards, background audit reason and process labels; the evidence export returned records, observations and events. Rebuilds caused expected temporary polling connection errors, which cleared after restart. Earlier failures remain preserved; no cloud deployment was changed.

### Runtime and evidence notes

The final water decision took 9.6 seconds; follow-ups took about 9.8 seconds each. Ollama reported roughly 2.4 seconds of load time for each follow-up with the reviewer active. This identifies runtime/model residency as a latency investigation, not proof of a hardware bottleneck. Replays and live audited loops are different workloads; their timings are not a controlled speed comparison.

`artifacts/model-review-v4/live-runtime-provenance.json` preserves the tested runtime sources and container image identities. `scheduler-fix-provenance.json` records the later scheduler correction and its rebuilt runtime. Exact requests and emitted replies are in the decision/audit records. Local screenshots show both the numeric command and Gemma's false flag; the JSON export retains all review and process evidence.

## Reproduce and inspect

```sh
.venv/bin/pytest -q
npm run build --prefix web
# These commands refuse existing output files/manifests.
.venv/bin/python -m scripts.evaluate_model_improvements --kind decision --variant bounded
.venv/bin/python -m scripts.evaluate_model_improvements --kind audit --variant audit-binary
.venv/bin/python -m scripts.evaluate_model_improvements --kind audit --split confirmation --variant audit-binary
.venv/bin/python -m scripts.evaluate_model_improvements --kind decision --split confirmation --variant bounded --root artifacts/model-review-v3 --case-file artifacts/model-review-v3/cases.json
```

To repeat a live trial, use a new output filename, an idle/disarmed local bench and a scoped keep-awake session. Select the package for both services, then wait for `/api/status` to report that package with a current snapshot:

```sh
PROCESS_PACKAGE=cooling docker compose up -d
caffeinate -i .venv/bin/python scripts/verify_improved_live_loop.py --output artifacts/review-new-cooling.json
# Restore water after the test has finished and cleaned up.
PROCESS_PACKAGE=water docker compose up -d
```

For a water run with background Gemma review, add `--policy observe`. The test stops/reset/disarms its bench afterward. The frozen local replay inputs are private artifacts; retain them when reproducing the recorded scores. New replays of used cases are regression checks, not fresh test evidence.

All outputs, including rejected candidates and the failed recovery, remain local. Exact inputs, raw replies, correction traces, model digests and hashes are saved. The final candidate additionally saves source files with its manifest. No weights were trained and no cloud service was changed.
