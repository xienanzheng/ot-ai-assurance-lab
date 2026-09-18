# Contributing

Start with an issue describing the question, reproducible synthetic scenario and expected result. Contributions can improve process models, memory retrieval, evaluation methods, accessibility or documentation. Keep changes bounded and state what the simulator cannot establish.

Run `docker compose --profile test run --build --rm test-runner`, `node --test tests/*.test.mjs`, and `npm ci && npm run build` in `services/web`. Optional interpretability tests require their separately documented environment. Never submit operational credentials, facility-specific topology, personal conversations or real plant telemetry.

Behaviour changes should include a failing regression test and a passing implementation. Control changes need explicit consideration of stale state, mode changes, lease expiry and retained deterministic protection. Do not promote a model explanation, reviewer agreement or one successful run into a safety claim.

By submitting a contribution, you agree to license your original contribution under the project's MIT licence. Preserve third-party notices. Review discussion should remain respectful, specific and focused on evidence.
