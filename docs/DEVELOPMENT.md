# Developer quick start

Install Node.js **22.12+**, Python **3.12 or 3.13**, Git and Docker Desktop. Then:

```sh
git clone --branch docs/friends-quickstart https://github.com/xienanzheng/ot-ai-assurance-lab.git
cd ot-ai-assurance-lab
npm install
npm run setup
```

`npm install` installs both React frontends from their lockfiles. `npm run setup` creates the workshop's Python environment and initializes the main lab's `.env` only if absent. Neither command downloads weights, calls a paid API or starts training.

## Choose what to edit

| App | Start its backend | Run editable frontend | Open |
|---|---|---|---|
| Main water / nuclear / grid lab | `npm run lab:up` | `npm run dev` | http://127.0.0.1:18773 |
| Water / cooling training workshop | `npm run bench:up` | `npm run dev:workshop` | http://127.0.0.1:18791 |

Run the backend command first, then the frontend command. Save your React/CSS changes and the browser updates. Ports 18780 and 18790 serve the respective built Docker apps; use the development ports above while editing.

For stock local AI, install and start Ollama, then `ollama pull qwen3:4b`. You can use the workshop fixture or the main lab's baseline controls without a model. See [installation and troubleshooting](QUICKSTART.md) for Linux networking and the optional auditor.

## Where to make changes

| Change | Location |
|---|---|
| Main interface | `services/web/src/` |
| Main simulator SOPs | `services/supervisor/app/plant_sops.json` |
| Workshop interface | `workshops/local-qwen/web/src/` |
| Workshop SOPs and relationships | `workshops/local-qwen/process_packages/` |
| Workshop context and audit | `workshops/local-qwen/v2/` |
| Local training and evaluation | `workshops/local-qwen/training/` |

After changing Python or process packages, stop feedback and rerun the relevant backend command to rebuild. It does not automatically hot-reload Python or modify a trained model. Work in a new Git branch before changing experiment inputs.

```sh
npm run test:tools
npm run test:workshop
npm run review
npm run build
npm run build:workshop
npm run doctor
```

`npm run package` creates an editable **standalone workshop** tarball under `release/`; it does not include the larger three-domain lab. For the full source, share this GitHub branch or download its ZIP. [Workshop npm commands](../workshops/local-qwen/DEVELOPMENT.md) include optional MLX setup and training stages.

Stop with `npm run lab:down` or `npm run bench:down`. Both retain their database volumes. Unrelated services are not stopped. The npm helpers do not publish to npm, deploy to Cloudflare, or promote an adapter.
