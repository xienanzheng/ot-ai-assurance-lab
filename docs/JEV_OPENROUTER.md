# Jev through OpenRouter

The local credential is `OPENROUTER_API_KEY` in the repository's ignored `.env.local` (owner read/write only). The hosted simulator Worker `ot-ai-assurance-demo` has its own Cloudflare secret binding with the same name. Cloudflare does not read files from the developer's computer. Secrets are never VITE-prefixed, bundled in browser assets, stored in the visitor database or committed.

Use `POST https://openrouter.ai/api/alpha/decisions` with `model`, `state` and typed `questions`; this is not the chat-completions request shape. The configured alias is `~typesafe/jev-latest`. Record the resolved model version in evaluation results; pin a supported version for controlled comparisons rather than allowing an alias to change between trials.

Run the local simulated connectivity check:

```sh
python3 scripts/check_jev.py
```

This makes one small billed request, sends only simulated data, and applies no controls. It reports typed answers, served model, latency and usage without printing credentials. On 25 September 2026, one successful check selected `request_review` for a stale-sensor scenario, resolved to `typesafe/jev-1.13-20260917`, took 0.369 seconds end to end, and reported $0.000016212. This explicitly instructed example is a connectivity check, not a control-quality or latency benchmark.

The analysis model switch offers Qwen and Jev (pinned `typesafe/jev-1.13`). Selecting a provider preserves the plant and existing records. Qwen generates structured targets; Jev chooses one bounded candidate generated from current targets, including explicit hold/review choices. The candidate descriptions are adapter text, not generated reasoning. Both pass through the independent deterministic gate.

“Run & apply through gate” enables gated control without resetting the plant, disables scheduled model decisions for that manual workflow, captures current state, and rechecks freshness and protection conditions before applying. Targets have a five-simulated-minute lease. Expiry restores previous targets; measurements do not reset or necessarily recover. HMI controls display live targets. A paused simulation must advance for measured process response and lease expiry.

“Compare both” captures once and makes two evaluation-only calls. It consumes two inference credits and spaces hosted calls to respect the ten-second rate limit. The user can select one proposal for fresh gate evaluation; changed runs, expired proposals, duplicate selection and rejected decisions cannot apply. The comparison is between different decision spaces, not a controlled benchmark of model quality. Session JSON exports include model requests, responses, candidate choices, gates, application records and subsequent observations (up to the latest 100 records).

Hosted Jev traffic passes through the Worker’s fixed OpenRouter endpoint using its secret; containers and browsers never receive that credential. The shared hosted allowance remains ten AI calls per session, three concurrent sessions and twenty new sessions per UTC day. Scheduled hosted inference is disabled. Provider failures do not bypass the gate or trigger silent fallback. Local Jev uses the ignored local credential and requires Internet access; local Qwen remains on Ollama.

For rotation, update the local ignored file and send the replacement to `wrangler secret put OPENROUTER_API_KEY --config deploy/cloudflare-live/wrangler.jsonc` via stdin. Do not put secret values in command-line arguments, documentation or screenshots. The homepage Worker does not need this credential.

Official references:
- https://openrouter.ai/docs/guides/community/jev
- https://developers.cloudflare.com/workers/configuration/secrets/
