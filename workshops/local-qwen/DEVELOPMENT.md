# Edit the workshop with npm

Install Node.js **22.12+**, Python **3.12 or 3.13**, and Docker Desktop. Ollama is optional until you want a real model call. This is an editable source package; it is not published to the npm registry.

Extract the ZIP or tarball, open a terminal in the folder containing `package.json`, then:

```sh
npm install
npm run setup
npm run bench:up
npm run dev
```

Open **http://127.0.0.1:18791**. Save a change in `web/src/main.jsx` or `web/src/style.css`; Vite updates the page. The Docker backend stays on **18790**. `/api` requests are proxied to it, including the Host/Origin needed by its checks.

- `npm install` installs the web dependencies from the included lockfile. It does not download model weights, create a Python environment or start Docker.
- `npm run setup` creates `.venv` and installs the Python test dependencies. An existing environment is preserved and checked.
- `npm run bench:up` builds and starts the separate `ot-qwen-workshop` Docker project, generating local credentials on first use.
- `npm run dev` runs the frontend with live reload. It needs the backend for sensor data.

If 18790 or 18840 is occupied by another V2 bench, stop that instance before starting the workshop. The developer frontend uses 18791 and fails clearly if its port is occupied.

## Common changes

| Edit | File | Check |
|---|---|---|
| Layout and controls | `web/src/main.jsx` | Save; inspect the page |
| Colours and spacing | `web/src/style.css` | Save; inspect the page |
| SOP, units, timing, bounds | `process_packages/water.json` / `cooling.json` | `npm test`, then rebuild bench |
| Decision context | `v2/decision_context.py` | `npm test`, then rebuild bench |
| Auditor instructions | `v2/providers.py` | Tests plus fresh audit cases |
| Training cases / labels | `training/bench_cases.py` | `npm test`; freeze a new experiment |

Frontend edits reload automatically. Python and process-package edits require `npm run bench:up` to rebuild the Docker image. Stop active feedback before rebuilding. Do not change an experiment's inputs after its prepare stage.

## Commands

```sh
npm run doctor        # Check Python, Docker and optional Ollama
npm test              # Python unit/contract/experiment tests
npm run test:tools    # Cross-platform npm helper tests
npm run review        # Recompute the saved 96-case comparison
npm run build         # Build the React frontend
npm run bench:down    # Stop this workshop; retain its database
npm run package       # Make release/airgap-ai-local-qwen-workshop-0.2.0.tgz
```

The tarball includes editable source, tests, SOPs, guides and recorded simulated results. It excludes `.env`, virtual environments, model weights, generated experiment folders and node_modules. Extract it before editing; do not install it globally. The GitHub ZIP also includes npm lockfiles.

For real inference, install Ollama, keep it running and run `ollama pull qwen3:4b`. Optional audit: `ollama pull gemma3:4b`. These are stock models. The **fixture** option needs neither model and is useful for checking integration.

## Optional training commands

On Apple Silicon, after reading [TRAINING.md](TRAINING.md):

```sh
npm run train:setup
npm run train:model
npm run train -- --stage prepare --root artifacts/my-new-run
```

Continue with `baseline`, `train`, `validate`, `test`, `report`, using the same root. Stage arguments reach the existing Python runner; its freezing, validation-only selection and no-overwrite checks still apply. The helper selects the pinned base snapshot and forces offline mode for stages. Nothing deploys the adapter. Training setup/downloads are explicit; `npm install` never starts them.

Keep the Mac awake during long stages, for example `caffeinate -i npm run train -- --stage train --root artifacts/my-new-run`. The original environment used Python 3.13; use `OTLAB_PYTHON` to select that interpreter if needed.

If you installed with `npm install --ignore-scripts`, run `npm --prefix web ci` before `npm run dev`. If Python is missing, install 3.12/3.13; no global Python or OS packages are installed by the helper. The MLX training path remains Apple Silicon-specific; npm does not convert it to CUDA.
