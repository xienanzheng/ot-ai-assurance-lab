# Water critical operator response

Qwen and Jev must explicitly return/select a structured operator response for critical conditions. This live contract is separate from the frozen water-alarm training benchmark; it does not claim the existing adapter was trained on these new fields.

Qwen returns `operator_response` alongside its decision. Jev's typed API answers an additional `operator_response` choice, selecting the supplied SOP plan. The server validates the selection and expands SOP IDs into readable guidance. This is constrained SOP selection, not evidence that either model independently diagnosed a root cause.

The contract contains `recommended_actions` (SOP reference IDs), `evidence_alarm_codes`, an explicit uncertainty statement, `monitoring_plan`, and `operator_intervention_required: true`. Escalation requires no executable changes. Missing, invented, duplicated or incompatible references fail validation. Raw provider responses remain in audit exports.

Guidance is displayed in the analysis record with its monitoring window, prerequisites and SOP version/hash. Valid selections are labelled **model-selected SOP guidance**. On inference failure, the server supplies separately labelled **server fallback SOP guidance** when the captured plant requires intervention; this does not count as a valid model response.

The PLC endpoint independently blocks AI actuation for critical alarms, critical state, emergency stop, active injected overrides, latched trips or an escalation decision. Frozen evaluation also rejects these states. Operator-response records cannot be applied using the record-application endpoint. Recommendations cannot reset protection or clear an override.

SOPs are simulator-code-grounded and are not plant-operator-validated procedures. Monitoring starts immediately; the observation window applies after operator-authorized recovery. Elapsed time alone never authorizes recovery.

## Reproduce checks

```sh
.venv-interpret/bin/python -m pytest tests/test_water_escalation_plan.py -o addopts='' -q
node --test tests/hosted-policy.test.mjs tests/cloudflare-demo.test.mjs
VITE_HOSTED=true npm --prefix services/web run build -- --outDir dist-hosted
```

Provider tests use controlled HTTP responses, exercise both HOSTED_MODE settings, and check accepted plans and missing-plan rejection. They establish enforcement, not actual model accuracy. Cloudflare's Jev proxy explicitly preserves and bounds the additional question.

## Verification recorded 2026-09-28

- Full Python regression: 258 passed, 3 integration skips. Subsequent status-import/candidate checks: 50 passed. Hosted policy and static demo tests: 14 passed.
- Local and hosted frontend builds passed. The Cloudflare container build and deployment succeeded; deployed version `7fbe22ee-d512-4888-b786-eee074f48204`.
- Live hosted scenario: `zone_2_valve_forced_closed`, one fresh isolated session, evaluated without application. Both Qwen and Jev completed with explicit model-selected SOP guidance, three recommendations, `operator_intervention_required: true`, `episode_status: escalate`, rejected actuation and `applied: false`. The status endpoint returned successfully. The test session was ended.
- Running local PLC endpoint rejected an escalation proposal and retained identical targets. The local supervisor health/status endpoints passed after updating its code and container-path handling. Local provider contract tests use mocked responses; no additional local model inference was run alongside the ongoing benchmark.
- Early cloud checks reached the previous rollout or a broken status import; neither counted as a passing check. The import was fixed and the fresh-session check above passed.

This is one live scenario check, not a measured improvement in general model accuracy or a safety certification. SOP wording is code-derived; the model explicitly selects/returns its references. The ongoing frozen training evaluation remains separate.

The final focused contract suite passed 30 tests; the corrected standalone web Docker build also passed. The sanitized live result is saved in `docs/evidence/water-operator-response-live-2026-09-28.json`.

Live verification used clearly marked test registrations (`ot-lab-check@example.invalid`, no contact consent). Cleanup was attempted, but the current Wrangler credentials were denied D1 query access (7403); those test registrations remain and should be excluded from audience counts.

All three updated local Docker images (web, supervisor, PLC) built successfully. A fresh supervisor image loaded its packaged SOPs and returned an intervention plan; the unapproved training candidate remained unavailable.
