# Package verification — November 10, 2026

- Installed `.[test]` into a fresh Python 3.13 virtual environment.
- Workshop tests: **150 passed**, one upstream Starlette/anyio deprecation warning.
- Root configuration-helper tests: **2 passed**; existing settings preserved; new local credentials created privately.
- Training requirements resolved with `pip --dry-run` on Apple Silicon. The training environment was not installed or rerun for this packaging task.
- Saved evaluation hashes checked; recomputed 32/96 base and 41/96 candidate decisions, with 0/32 candidate holds and readiness false.
- Main Compose configuration validated; isolated V2 Docker images built and started successfully.
- V2 web returned HTTP 200. Fixture proposal reached the controller, received an applied acknowledgement and read back target **1.0 mg/L**. Measured residual decreased from **1.3966** to **1.3497 mg/L** over the short observation. This checks integration, not sustained recovery or model quality.
- Used a separate Docker project on ports 18796/18846; no existing lab reset or model call.
- New package checked for credential patterns; credentials, weights and private visitor/presentation files excluded.

The Mac checks do not establish native Windows/Linux installation success. GitHub CI is configured to run the CPU checks on Linux. No new GPU training, teacher calls, adapter promotion, site deployment or physical-plant test was performed.
