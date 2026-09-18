# Exercise upgrade validation — 2026-09-07

The offline container suite collected 80 tests: 77 passed and 3 opt-in live
integration tests were skipped. WNTR and third-party deprecation warnings remain;
the tests cover the reduced-order model behavior rather than site calibration.
The complete build/test output is in `artifacts/validation-tests.log`.

Separate live API checks verified water PLC stepping and pause/resume, preserved
nuclear/grid elapsed time during speed changes, rejection of unknown scenarios,
and complete minute-by-minute exports. `artifacts/validation-summary.json`
contains the outcomes.

| Saved exercise | Minutes | Samples | Critical minutes | Selected result |
|---|---:|---:|---:|---|
| Water normal day, baseline, seed 42 | 10 | 11 | 0 | 0 m³ unserved water; 35.9634 kWh |
| Nuclear coolant-pump trip, baseline | 90 | 91 | 69 | First-out low primary-loop flow at minute 22 |
| Grid generator trip, baseline | 90 | 91 | 56 | 104.5269 MWh unserved energy |

These are synthetic scenario outcomes, not physical validation measurements.
All three exercises were left paused, and all application services were healthy.
The final JSON records are `artifacts/exercises/water-verified-final.json`,
`nuclear-verified-final.json`, and `grid-verified-final.json`.

Browser checks verified navigation, operator-note submission, alarm
acknowledgement without clearing protection, domain-specific alarm status,
desktop/mobile layout and no reported browser errors. Screenshots are saved as
`artifacts/exercise-console-water.png`, `exercise-console-nuclear.png`,
`exercise-console-grid.png`, and `exercise-console-mobile.png`.

The previous running lab state and available active-run export were preserved
under `artifacts/pre-upgrade-20260907-222100` before service replacement.
