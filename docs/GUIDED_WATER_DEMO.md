# Water monitoring demo

Open **AI decisions → Water agent** and choose **Water exercise**: **Chlorine residual adjustment**, **Chlorine overdose** or **Rising filtered-water turbidity**. Choose Qwen or Jev, set a call budget (at least two for a repeat analysis), choose a demo clock (10× by default), then click **Start monitoring & control**. This resumes the selected exercise without resetting it. The previous special guided-run button has been removed.

Chlorine residual and the baseline PLC target start at **1.15 mg/L**. The **0.90–1.00 mg/L** band is the adjustment exercise goal. The panel shows a **yellow high alarm at ≥1.50 mg/L** and a **red high-high alarm at ≥2.00 mg/L**, from the same versioned configuration used by the simulator and agent context. Yellow allows consideration of a gated reduction; red requires escalation and operator recommendations without automatic actuation. The broader 0.20–4.00 mg/L process envelope remains in code but is not displayed in this panel. Lower-residual and CT protections remain active. **Chlorine overdose** is a separate selectable exercise: the existing overfeed fault begins at minute 10 for 60 simulated minutes and requires operator intervention. It can also be injected from Water HMI. Turbidity uses the filtered-water sensor and its 0–1 NTU operating band; the coagulant target is displayed separately in mg/L.

Monitoring shows the current owner, next review minute and remaining simulated minutes. Chlorine adjustments require 12 simulated minutes before re-analysis (14-minute lease); other actions use their existing process-specific windows. A single **Run & apply through gate** remains one call with a five-minute lease, not an automatic feedback loop. Pausing the clock also pauses feedback. The final AI call is followed by its full observation window. Then the controller returns to baseline while sensor trends continue until operator stop, a critical condition, or the 90-simulated-minute/15-wall-minute monitoring limit. Measurements may move back toward the baseline target.

The exercise objective is residual chlorine of **0.90–1.00 mg/L**. A normal safety state does not mean that this efficiency objective is satisfied. The agent receives the measured objective gap, SOP prerequisites, the direction of the target-to-process relationship, prior actions, recent observations and simulator-derived response windows. Both interfaces limit this exercise to chlorine-target adjustments, hold or escalation. Other water scenarios retain their existing control vocabulary.

The live panel separates the measured residual, exercise objective, current PLC target, selected exchange's proposal, actual application and monitoring status. Open **Water HMI** to inspect the same PLC targets and process. Structured JSON and full-record/session export remain available under decision evidence. The plotted band is an objective, not a recovery claim.

## Sensors to watch

In **Exercise console → Sensor**, select **chlorine_residual_mg_l** for the treated-water outcome. Check **chlorine_dose_actual_mg_l** for delivered dosing and **chlorine_ct_mg_min_l** for disinfection contact exposure. **Add sensor** compares up to four sensors on a shared timeline, each with its own scale and unit. Remove a comparison with ×. Selections are remembered separately per domain across navigation and refresh.

With seed 42 and baseline control, the adjustment exercise starts at 1.150 mg/L and measures about 1.097 mg/L at minute 15; it has no programmed rising-dose fault. The overdose exercise forces 5.0 mg/L delivered dose at minute 10, giving approximately 1.343 mg/L residual at minute 10 and 2.272 at minute 15. The independent feed-mismatch alarm can make that scenario critical before residual reaches either high threshold. These are deterministic simulator checks, not new model evaluations.

Alarm configuration `water-chlorine-alarms-v1` and SOP 1.1.1 apply to new runs. Historical benchmark records retain their original inputs and versions; this change does not re-score or improve those model results.

## Timing and authority

- In feedback mode, a chlorine adjustment has a 12-minute earliest review and a 14-minute maximum lease, derived from simulator coefficients. These are simulated minutes, not physical-plant calibration.
- A one-off application retains its five-minute lease. Requests and Jev candidate descriptions disclose the applicable lease separately from the process observation window.
- Target changes do not move sensor readings instantly. The baseline controller operates the dosing loop, and plant dynamics determine the observed response.
- Lease expiry or stopping feedback restores prior targets. The residual can rise again after an efficiency trim expires; entering the band temporarily is not permanent normalization.
- A water hold rejected **only** for low confidence may continue bounded read-only monitoring after baseline return. The loop never automatically rearms. Subsequent proposals are evaluation-only.
- A rejected executable change, other protection failure, invalid response, critical transition, reset or operator stop still ends feedback. Model confidence is never increased by the adapter.
- Ending a loop finalizes unfinished observation records. Audit-write failure cannot prevent an attempted baseline return. Late completed decisions remain attached to the ended loop.

`POST /api/v1/agents/water/feedback` accepts `start_clock: true`, optional `simulation_speed` (10, 20, 30 or 60) and `monitor_after_budget: true` to resume the current exercise. The legacy `POST /api/v1/agents/water/guided` remains API-compatible but is no longer exposed as a UI button. It reserves supervision before setup, rejects overlapping loops/jobs and pauses/releases on setup failure. `POST /api/v1/agents/feedback/stop` ends the loop. The existing hosted session and inference budgets still apply.

## Verification

Run:

```sh
.venv-interpret/bin/python -m pytest tests -o addopts='' -q
node --test tests/*.test.mjs
VITE_HOSTED=true npm --prefix services/web run build -- --outDir dist-hosted
```

Regression coverage includes focused action contracts, yellow/red alarm boundaries, yellow-state gated reductions, red-state rejection, low-residual protection, accurate timing, bounded read-only continuation, rejected-action stops, critical stops, concurrent disarming, late completion after stop, guided setup ownership/failure, and audit finalization.

Live development runs and screenshots are retained privately under `artifacts/guided-water-20260930/` (Git-ignored). These are integration evidence, separate from the locked water-alarm benchmark. Context and control-interface changes do not constitute new model weight training, and no model is guaranteed to select or complete an optimization.
