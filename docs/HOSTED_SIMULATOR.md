# Hosted simulator and recorded demo

The recorded research site is at https://ot-aigent-simulation.night-zone.com. Its current static deployment serves saved synthetic evidence. It has no connection to a local simulator, database, or Ollama service.

The separate `deploy/cloudflare-live` package prepares the actual simulator for Cloudflare Containers. **Deployment requires Workers Paid.** An API model avoids hosting model weights; Python simulation engines still need container compute. The hosted package uses the existing water, nuclear and grid engines and deterministic gates, bundled into one isolated container per visitor. SQLite and simulator state are private to that temporary container.

## Online versus offline

| | Local lab | Public hosted sandbox |
|---|---|---|
| Inference | Ollama / locally downloaded weights | Cloudflare Workers AI API |
| Default model | Qwen3 8B | Qwen3 30B-A3B FP8 |
| Memory | Local historian and reviewed lessons | Temporary session evidence; shared lesson retrieval off |
| Control | Same deterministic gates | Same deterministic gates |
| Connectivity claim | Can be studied offline after provisioning | Internet-connected; not air-gapped |

The hosted model is a different model and execution environment. Do not combine its results with local-model experiments without explicitly identifying this difference. Hosted requests use an Ollama-compatible adapter for the existing client, while audit records identify `cloudflare-workers-ai`, cloud execution, and the actual model. Model-emitted explanations are observable outputs, not proof of the model's complete or faithful chain of thought. Hosted mode requests concise final rationales, not mechanistic activation captures.

## Initial usage limits

- Three active sessions, each expiring after 20 minutes; five-minute idle sleep.
- Twenty new sessions per UTC day across the whole demo.
- Ten AI requests per session; 200 per UTC day; ten seconds between requests.
- 2,048 output tokens and 50 KB of inference input per call.
- 180 API requests per session per minute; request bodies limited to 64 KB.
- Batch alignment studies remain local-only. Single evaluations and gated actions are supported.

The session registry serializes and persists quota reservations. Failed inference attempts consume allowance. The API cannot choose another model or increase output limits. A secure HttpOnly, same-origin cookie selects a server-issued session; callers cannot supply another container ID. Expired containers are destroyed before their capacity is reclaimed. Sessions are not user accounts, and anonymous visitors could exhaust daily availability. These are application usage caps, not a guaranteed dollar billing cap.

The container's public internet access is disabled. The only allowed egress hostname, `inference.lab`, is intercepted by trusted Worker code using an AI binding. No API credential is supplied to the browser or container. Cloudflare processes synthetic sensor context, operator-entered notes included in that context, and model outputs. Do not enter operational or personal data.

## Build and deploy the full version

```sh
npm --prefix services/web ci
VITE_HOSTED=true npm --prefix services/web run build -- --outDir dist-hosted
python3 scripts/build_cloudflare_demo.py --live
npm --prefix deploy/cloudflare-live ci
cd deploy/cloudflare-live
npx wrangler login
npx wrangler deploy --dry-run
npm run deploy
```

The live configuration updates the same Worker/custom domain as the recorded deployment. It replaces the replay-only root with a session-start screen and preserves `/research.html`. Enable Workers Paid before the final command. The configuration does not use a tunnel to anyone's computer. Set a Cloudflare billing alert and review measured usage after the first audience session.

For local container testing:

```sh
docker build -t ot-ai-hosted-lab:test -f deploy/cloudflare-live/Dockerfile .
docker run --rm -p 127.0.0.1:18880:8080 ot-ai-hosted-lab:test
```

This standalone container verifies simulation services. Its special inference hostname requires the Worker outbound adapter; without it, AI is unavailable and deterministic control remains active. Use `npx wrangler dev` inside `deploy/cloudflare-live` to exercise Worker session routing and the outbound adapter locally with Docker. Workers AI binding requests use cloud inference and may be billed.

The public session UI waits for startup, labels cloud inference, shows the session deadline, and unmounts the simulator when the deadline is reached. Export evidence before ending a session. Sleep, expiry or container restart can discard its ephemeral data.

## Recorded-only deployment

```sh
npm --prefix services/web run build
python3 scripts/build_cloudflare_demo.py
npx wrangler deploy --config deploy/cloudflare/wrangler.jsonc
```

Raw activation NPZ files remain in GitHub; the hosted static bundle omits them because of the per-file asset limit. The dashboard says this explicitly.

References: [Cloudflare Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/), [outbound handlers](https://developers.cloudflare.com/containers/guides/outbound-traffic/), [Qwen API model](https://developers.cloudflare.com/workers-ai/models/qwen3-30b-a3b-fp8/).
