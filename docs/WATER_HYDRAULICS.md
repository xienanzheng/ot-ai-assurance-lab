# Water hydraulic response — version 2

Implemented and installed in the local Docker lab on 2026-09-29. These are simulator relationships, not calibrated utility parameters or a transient pressure analysis. No model training or hosted deployment is part of this change.

## What changed

Manual commands, PLC/AI actuator commands and injected field overrides now feed the same treatment hydraulic calculation. The `pump_valve_conflict` injection sets actual equipment state (closed outlet and minimum 75% intake speed); it no longer writes a special pressure or multiplies flow by an arbitrary fault factor.

The treatment model solves the intersection of an illustrative centrifugal pump curve and a quadratic system resistance:

```
pump head [m] = 50 × (speed [%] / 100)² − 0.00018 × flow [m³/h]²
system head [m] = receiving head + (pipe + intake valve + filter + outlet valve resistance) × flow²
receiving head [m] = 2 + 0.03 × clearwell level [%]
```

Forward flow is zero with a stopped pump, closed suction/outlet or unavailable filter train. Reverse flow is excluded by the model's check-valve assumption. An open suction and blocked outlet with a running pump produce finite shutoff head and a critical deadhead alarm, regardless of whether the condition came from a manual command or an injection. Closing the suction is treated as loss of supply, not outlet deadheading; cavitation is not simulated.

Filter fouling is retained as resistance at a 280 m³/h reference flow; measured filter differential pressure depends on actual flow. The valve display excludes the upstream filter-media pressure loss. Closing the treatment outlet reduces clearwell inflow; the independent high-lift pump can continue supplying the network from storage.

Valve travel remains limited to 12 percentage points per simulated minute. Distribution calculations now run every simulated minute. WNTR is reset before each instantaneous solve, so repeated calls do not exhaust its internal simulation clock or integrate tank storage a second time. Fully closed zone valves are closed links, and stopped high-lift pumps are closed supply paths. The analytical fallback remains available and is labelled in the snapshot.

SOP version 1.1.0 describes these relationships. The minimum pressure review window remains five minutes; a one-minute hydraulic update is not permission to issue another AI command. Gate limits, critical-state actuation prohibition and operator intervention requirements are unchanged.

## Recorded closure and reopening

Seed 42; ten-minute warm-up; fixed pump commands; no PLC or AI correction. Close the filter outlet at minute 1; reopen at minute 16. Results below are from the analytical fallback run. The Docker WNTR run produces the same treatment trajectory, with its own distribution pressures.

| Minute after warm-up | Treatment flow (m³/h) | Upstream pressure (kPa) |
| --- | ---: | ---: |
| 0 | 269.5 | 123.3 |
| 1 | 264.2 | 128.4 |
| 5 | 199.8 | 182.2 |
| 8 | 0.0 | 254.2 |
| 10 | 0.0 | 254.2 |
| 16 | 90.3 | 239.5 |
| 25 | 268.9 | 123.9 |

Pressure approaches the pump's finite shutoff head rather than increasing forever. Distribution continues from storage during this closure; the clearwell falls. Reopening reverses the pressure/flow relationship over valve travel time.

The trajectory script also records a baseline, matched manual/injected configurations, Zone 2 closure, intake pump shutdown and a chlorine-dose step. Its assertions check identical matched hydraulics and combined storage balance. JSON/CSV include the simulator source hash, model version, actual engine and any hydraulic errors. The chart shows measured simulator output, not a predicted real-plant curve.

## Reproduce

```sh
.venv-interpret/bin/python -m pytest
.venv-interpret/bin/python scripts/verify_water_hydraulics.py --plot
docker compose --profile test run --build --rm --no-deps test-runner pytest -rA
```

To collect WNTR trajectories in the existing plant image, using current source without altering a running session:

```sh
mkdir -p artifacts/water-hydraulics-v2
docker run --rm --network none \
  -v "$PWD:/work:ro" \
  -v "$PWD/artifacts/water-hydraulics-v2:/evidence" \
  -w /work -e PYTHONPATH=/work water-ot-ai-lab-plant-sim \
  python scripts/verify_water_hydraulics.py --engine available --output /evidence --plot
```

`available` uses WNTR if installed; check recorded engine and error fields rather than assuming it did. The regular virtual environment lacks WNTR; its three WNTR-specific regression tests are exercised in Docker instead. The test image now includes the generated SOP book, fixing the previously missing-file failure in its documentation consistency test.

## Limits and experiment provenance

- The treatment calculation is a simplified, quasi-steady series circuit. It omits clarifier/filter vessel inventories, calibrated residence-time distributions, pipe elasticity, sub-minute water hammer, cavitation and pump heating/damage.
- Distribution remains a hybrid: WNTR or analytical pressures plus separate capacity, service-allocation and bounded gravity-flow formulas. It is not yet one calibrated network-wide flow/storage solution; the fallback is not numerically equivalent to WNTR.
- Chemical response still uses the existing first-order pH/chlorine updates; coagulation lacks calibrated transport delay. This change tests the existing chlorine lag and flow interlock, rather than claiming a new reaction/transport model.
- WNTR/dependency warnings about legacy resource loading and curve fitting remain. Existing unrelated grid/nuclear test fixtures also produce Pydantic serialization warnings.
- Frozen training, development and locked-test artifacts were not regenerated. Their reported scores refer to their original snapshots and source versions. New dynamic experiments must record `water-hydraulics-v2` and SOP 1.1.0; they must not be mixed silently with old trajectories.
- The local plant and supervisor containers were rebuilt, the web proxy reloaded, and the public-facing local state endpoint confirmed `water-hydraulics-v2`. The supervisor loaded SOP 1.1.0 and the PLC reported an active OPC UA connection. The lab was left paused at minute zero. The public Cloudflare simulator remains on its previous deployment.

## Verification result

- Local Python suite: **278 passed, 6 skipped** (three opt-in live integration checks and three WNTR checks; WNTR is tested in Docker).
- Docker Python suite: **278 passed, 6 skipped** (three opt-in integration checks and three optional interpretability checks). All 14 new hydraulic tests passed in Docker.
- Local live dashboard/API reachability test: **1 passed** after the container update.
- Trajectory collection: **217 samples per engine**, seven scenarios each; matching manual/injected hydraulics had zero difference and maximum combined storage-balance residual was below `8e-13 m³`. No hydraulic errors were recorded in either collection.
- Generated SOP book consistency and `git diff --check` passed. Existing dependency/fixture warnings are recorded in the test logs; no test failures remain.

Raw CSV/JSON, PNG/SVG/PDF charts and test logs are kept locally under the ignored `artifacts/water-hydraulics-v2/` directory. The standalone trajectories do not run the PLC or an AI model, so their numbers must not be described as AI recovery results.
