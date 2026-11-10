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

## npm developer package

- Root `npm install` installed both frontends using their lockfiles; `npm run setup` created a new workshop Python environment.
- `npm run test:workshop`: 150 passed. npm helper tests: 10 passed, including Windows Python discovery, argument boundaries and package exclusions.
- Main and workshop React production builds passed.
- `npm run bench:up` started the isolated `ot-qwen-workshop` project. The Vite UI at 18791 received JSON from 18790, accepted same-origin traffic and rejected a cross-origin request. A fixture proposal received an applied controller receipt for 1.0 mg/L through that proxy.
- A temporary visible source edit was served by Vite; the original source was restored afterwards.
- `npm run package` checked the file list before creating the tarball. Python caches, credentials, model weights, environments, dependencies and generated experiments were excluded.
- Extracted the tarball into a new folder; `npm install`, automatic ignore-rule creation and `npm run build` passed there.

These checks exercise the npm setup and integration path. They make no new claim about model accuracy or training performance.
