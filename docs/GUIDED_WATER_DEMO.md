# Guided water demo

Open **AI decisions → Water agent**, select Qwen or Jev and choose **Start guided water run**. This creates a fresh chlorine-efficiency exercise (seed 42), advances 15 simulated minutes under baseline control, reserves feedback ownership and starts the clock at 10× speed. Existing decision records remain available. The default budget is three model calls.

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

`POST /api/v1/agents/water/guided` accepts the existing feedback request. It reserves supervision before setup, rejects overlapping loops/jobs and pauses/releases on setup failure. `POST /api/v1/agents/feedback/stop` ends the loop. The existing hosted session and inference budgets still apply.

## Verification

Run:

```sh
.venv-interpret/bin/python -m pytest tests -o addopts='' -q
node --test tests/*.test.mjs
VITE_HOSTED=true npm --prefix services/web run build -- --outDir dist-hosted
```

Regression coverage includes focused action contracts, unchanged numeric protection, accurate timing, bounded read-only continuation, rejected-action stops, critical stops, concurrent disarming, late completion after stop, guided setup ownership/failure, and audit finalization.

Live development runs and screenshots are retained privately under `artifacts/guided-water-20260930/` (Git-ignored). These are integration evidence, separate from the locked water-alarm benchmark. Context and control-interface changes do not constitute new model weight training, and no model is guaranteed to select or complete an optimization.
