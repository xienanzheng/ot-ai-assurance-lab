# Water monitoring demo

Open **AI decisions → Water agent** and choose **Water exercise**: **Chlorine residual adjustment**, **Chlorine overdose** or **Rising filtered-water turbidity**. Choose Qwen or Jev, set a call budget (at least two for a repeat analysis), choose a demo clock (30× by default), then click **Start monitoring & control**. This resumes the selected exercise without resetting it. The previous special guided-run button has been removed.

For chlorine, the simulator's operating limits are 0.20–4.00 mg/L; the baseline PLC target is 1.15 mg/L. The narrower 0.90–1.00 mg/L band is an efficiency goal, not a high-chlorine alarm. The panel displays these separately. **Chlorine overdose** is a separate selectable exercise: the existing overfeed fault begins at minute 10 for 60 simulated minutes and requires operator intervention. It can also be injected from Water HMI. Turbidity uses the filtered-water sensor and its 0–1 NTU operating band; the coagulant target is displayed separately in mg/L.

Monitoring shows the current owner, next review minute and remaining simulated minutes. Chlorine adjustments require 12 simulated minutes before re-analysis (14-minute lease); other actions use their existing process-specific windows. A single **Run & apply through gate** remains one call with a five-minute lease, not an automatic feedback loop. Pausing the clock also pauses feedback. The final AI call is followed by its full observation window. Then the controller returns to baseline while sensor trends continue until operator stop, a critical condition, or the 90-simulated-minute/15-wall-minute monitoring limit. Measurements may move back toward the baseline target.

The exercise objective is residual chlorine of **0.90–1.00 mg/L**. A normal safety state does not mean that this efficiency objective is satisfied. The agent receives the measured objective gap, SOP prerequisites, the direction of the target-to-process relationship, prior actions, recent observations and simulator-derived response windows. Both interfaces limit this exercise to chlorine-target adjustments, hold or escalation. Other water scenarios retain their existing control vocabulary.

The live panel separates the measured residual, exercise objective, current PLC target, selected exchange's proposal, actual application and monitoring status. Open **Water HMI** to inspect the same PLC targets and process. Structured JSON and full-record/session export remain available under decision evidence. The plotted band is an objective, not a recovery claim.

## Timing and authority

- In feedback mode, a chlorine adjustment has a 12-minute earliest review and a 14-minute maximum lease, derived from simulator coefficients. These are simulated minutes, not physical-plant calibration.
- A one-off application retains its five-minute lease. Requests and Jev candidate descriptions disclose the applicable lease separately from the process observation window.
- Target changes do not move sensor readings instantly. The baseline controller operates the dosing loop, and plant dynamics determine the observed response.
- Lease expiry or stopping feedback restores prior targets. The residual can rise again after an efficiency trim expires; entering the band temporarily is not permanent normalization.
- A water hold rejected **only** for low confidence may continue bounded read-only monitoring after baseline return. The loop never automatically rearms. Subsequent proposals are evaluation-only.
- A rejected executable change, other protection failure, invalid response, critical transition, reset or operator stop still ends feedback. Model confidence is never increased by the adapter.
- Ending a loop finalizes unfinished observation records. Audit-write failure cannot prevent an attempted baseline return. Late completed decisions remain attached to the ended loop.

`POST /api/v1/agents/water/feedback` accepts `start_clock: true`, optional `simulation_speed` (10, 30 or 60) and `monitor_after_budget: true` to resume the current exercise. The legacy `POST /api/v1/agents/water/guided` remains API-compatible but is no longer exposed as a UI button. It reserves supervision before setup, rejects overlapping loops/jobs and pauses/releases on setup failure. `POST /api/v1/agents/feedback/stop` ends the loop. The existing hosted session and inference budgets still apply.

## Verification

Run:

```sh
.venv-interpret/bin/python -m pytest tests -o addopts='' -q
node --test tests/*.test.mjs
VITE_HOSTED=true npm --prefix services/web run build -- --outDir dist-hosted
```

Regression coverage includes focused action contracts, unchanged numeric protection, accurate timing, bounded read-only continuation, rejected-action stops, critical stops, concurrent disarming, late completion after stop, guided setup ownership/failure, and audit finalization.

Live development runs and screenshots are retained privately under `artifacts/guided-water-20260930/` (Git-ignored). These are integration evidence, separate from the locked water-alarm benchmark. Context and control-interface changes do not constitute new model weight training, and no model is guaranteed to select or complete an optimization.
