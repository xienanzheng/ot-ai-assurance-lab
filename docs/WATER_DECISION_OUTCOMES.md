# Water decisions: review, hold and bounded adjustment

Updated 2026-09-29. These are simulator integration checks, not a model benchmark or evidence of real-plant safety.

## What changed

- The inspection UI distinguishes operator review, hold, blocked proposals, inference/response failure, and approved/applied targets. The raw gate verdict remains in the exported evidence. A low-confidence empty proposal is displayed as **Hold · gate not authorized**, not as a rejected actuator command.
- Operator intervention lists the actual critical alarm codes, emergency stop, active override IDs and latched trip codes. A voluntary model review is explicitly distinguished from a mandatory protection trigger.
- Operator guidance is selected from observed alarms, trips and overrides. Unmapped conditions receive the general verification check rather than every water SOP. Critical-state model responses must still reference the required plan and contain no executable changes.
- Healthy Jev requests no longer contain a second mandatory intervention question. Healthy Qwen requests label review references optional. Both models receive the current operating objective; the efficiency exercise also provides a deterministic above/within/below-band comparison with sensor-quality and freshness checks. This comparison is code-derived evidence, not model diagnosis or actuation authority.
- Feedback asks for a hold when no adjustment is justified. It distinguishes model review from an invalid decision and retains the audit ID when inference fails.

## Repeatable exercise

1. Open **Exercise console → Water treatment**.
2. Select **Chlorine efficiency trim · AI adjustment**. This starts a fresh run. The scenario uses normal plant physics with a residual objective of 0.90–1.00 mg/L; it does not inject a protection override.
3. Click **Advance to minute 15**, then **Open AI decisions → Compare Qwen / Jev**. Compare captures one state for both and does not actuate.
4. Inspect the proposed targets, actual gate reasons and JSON. Models can still choose hold or review.
5. For a separate applied-response run, select one model, choose one feedback call, and start feedback. Start/resume the simulation. Inspect the HMI and the 12-minute chlorine observation window. Feedback uses a bounded response-aware lease, then returns to baseline. A one-off application uses the existing shorter five-minute lease.
6. Export the session and exercise records before resetting.

No confidence threshold, critical-state prohibition, sensor freshness check, trip latch, temporal lock or application permission was relaxed.

## Recorded checks

Local harness: seed 42, captured minute 15, production provider adapters and hosted request policy. Hosted Qwen3-30B-A3B and Jev 1.13 were called through their cloud APIs. A separate freshly seeded local simulator evaluated each returned proposal and its trajectory. These were development iterations, not independent held-out trials; all outputs were retained.

| Context revision | Qwen | Jev |
|---|---|---|
| Optional escalation catalogue | First transport failed with expired Cloudflare authentication; after refresh, empty hold with confidence 0.00 | Hold, accepted, confidence 0.55 |
| Objective promoted and disinfection-only SOP selection | Empty hold, confidence 0.00; incorrectly claimed residual was inside the objective | Hold, accepted, confidence 0.79 |
| Explicit measured objective position | Target 1.10 mg/L, confidence 0.75, gate accepted | Target 1.025 mg/L, confidence 0.47, gate rejected below 0.55 threshold |

The final Qwen response also echoed the unchanged pressure target of 44 m; the application service strips unchanged targets. No successful-decision retry was used within a revision. One authentication failure was retried after refreshing credentials. This context-development sequence does not establish a general improvement rate.

| At simulated minute 27 | Baseline | Qwen proposal applied | Code-defined reference trim |
|---|---:|---:|---:|
| Residual, mg/L | 1.0949 | 1.0556 | 0.9967 |
| CT, mg·min/L | 87.46 | 84.33 | 79.62 |
| Delivered chlorine mass over 12 minutes, g | 72.01 | 68.16 | 62.38 |
| Critical minute samples | 0 | 0 | 0 |

Qwen reduced chemical use by 5.35% relative to the seeded baseline over this window. Residual moved toward the requested band but did **not** yet reach it. The stronger reference trim is explicitly code-defined; it is not a successfully applied Jev result. Jev's blocked proposal left the baseline trajectory unchanged. Neither provider is guaranteed to repeat these decisions.

Raw records and every development revision are kept under `artifacts/water-efficiency-demo-20260929*` (ignored by Git). Model-emitted text, code-generated guidance, gate outcome and measured plant response are separate evidence.

## Reproduce

```bash
.venv-interpret/bin/python scripts/validate_water_efficiency_demo.py --output artifacts/water-efficiency-reference-new
# Optional: spends one live call per selected provider; uses local credentials without exporting them.
.venv-interpret/bin/python scripts/validate_water_efficiency_demo.py --live-models --providers qwen jev --output artifacts/water-efficiency-live-new
.venv-interpret/bin/python -m pytest tests/test_water_escalation_plan.py tests/test_water_efficiency_demo.py tests/test_feedback_loop.py tests/test_sop_context.py tests/test_model_switch.py tests/test_operations_and_agents.py tests/test_controller.py tests/test_water_alarm_candidate.py -q
node --test tests/decision-outcome.test.mjs tests/hosted-policy.test.mjs
```

The harness refuses to overwrite an existing report. It contacts no running simulator and issues no real-plant commands. Cloudflare credentials must be current; Jev uses the existing local secret lookup. This work changes context, diagnostics and the exercise UI, not model weights or the earlier locked-test results.

## Hosted release verification

Deployed to `ot-aigent-simulation.night-zone.com`, Worker version `d6e8827c-c431-4ba0-aa5d-b9b3c349b630`. The shared backend changes apply to local services after restart as well; no local model weights were changed.

The public-session browser check selected the exercise, advanced to minute 15 and compared both providers. Qwen chose an accepted hold (confidence 0.85); Jev proposed 1.025 mg/L and was blocked at confidence 0.49. Neither normal-state record was eligible for actuation in that run, so **hosted model actuation was not demonstrated by this check**. The approved Qwen adjustment and measured benefit above came from the controlled local replay of a live Cloudflare response.

A subsequent forced Zone 2 valve closure made both models escalate with exactly three checks: protection verification, pressure SOP and flow-path verification. No target changed. The UI displayed **Operator review** for both while retaining rejected raw gate verdicts. Desktop/mobile screenshots and full records are in `artifacts/water-efficiency-hosted-20260929/`. No browser runtime errors or mobile horizontal overflow were observed. The temporary session was ended and only the automated visitor entries were removed.

One initial browser run found an empty scenario list after a failed catalogue load. Startup catalogue reads now retry at most three times and surface an error on exhaustion; control and inference requests are never retried by that helper. Regression coverage: 137 Python checks, 29 JavaScript checks, hosted production build and live browser/API checks.
