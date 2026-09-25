# Jev through OpenRouter

The local credential is `OPENROUTER_API_KEY` in the repository's ignored `.env.local` (owner read/write only). The hosted simulator Worker `ot-ai-assurance-demo` has its own Cloudflare secret binding with the same name. Cloudflare does not read files from the developer's computer. Secrets are never VITE-prefixed, bundled in browser assets, stored in the visitor database or committed.

Use `POST https://openrouter.ai/api/alpha/decisions` with `model`, `state` and typed `questions`; this is not the chat-completions request shape. The configured alias is `~typesafe/jev-latest`. Record the resolved model version in evaluation results; pin a supported version for controlled comparisons rather than allowing an alias to change between trials.

Run the local simulated connectivity check:

```sh
python3 scripts/check_jev.py
```

This makes one small billed request, sends only simulated data, and applies no controls. It reports typed answers, served model, latency and usage without printing credentials. On 25 September 2026, one successful check selected `request_review` for a stale-sensor scenario, resolved to `typesafe/jev-1.13-20260917`, took 0.369 seconds end to end, and reported $0.000016212. This explicitly instructed example is a connectivity check, not a control-quality or latency benchmark.

Current integration boundary: the key is provisioned for the deployed Worker, and the local check works. The running simulator still uses Qwen. A Jev model selector, candidate-action adapter, quota integration and matched evaluation runner are separate implementation work; setting the secret alone does not switch models.

For rotation, update the local ignored file and send the replacement to `wrangler secret put OPENROUTER_API_KEY --config deploy/cloudflare-live/wrangler.jsonc` via stdin. Do not put secret values in command-line arguments, documentation or screenshots. The homepage Worker does not need this credential.

Official references:
- https://openrouter.ai/docs/guides/community/jev
- https://developers.cloudflare.com/workers/configuration/secrets/
