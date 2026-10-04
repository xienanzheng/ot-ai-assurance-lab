# Public-site crawler policy

Implemented 2026-09-30 on `securecritcticalinfra.dev` and
`ot-aigent-simulation.night-zone.com` only. Other `night-zone.com` services
are outside this policy.

## Implemented

- Both Cloudflare Workers call `deploy/crawler-policy.mjs` before assets,
  registration, session allocation or inference routes.
- Known AI collection, search and fetch user-agents receive HTTP 403. Responses
  are not cached. Ordinary browser requests and visitors following AI-platform
  links remain allowed; referrers are not used to block people.
- `/robots.txt` is readable by everyone (GET/HEAD). The homepage allows ordinary
  indexing, preserves its sitemap, and disallows the listed AI agents. The lab
  requests no crawling by any bot. This does not restrict human visitors.
- Google-Extended and Applebot-Extended are robots-only opt-out tokens;
  Googlebot, Bingbot, DuckDuckBot and Applebot are not HTTP-blocked.
- Turnstile is not enabled. Existing registration, session expiry, admission
  capacity and inference budgets are unchanged.

## Remaining managed protection

**This is user-agent matching in Cloudflare Workers, not Cloudflare managed AI
bot detection.** A crawler can evade the match by changing its user-agent.
Robots directives are voluntary. No claim of complete scraping prevention is
made, and these controls cannot recall content already collected.

The available Wrangler OAuth token can deploy Workers but cannot read or edit
Bot Management or WAF rulesets: both APIs returned 403 authentication errors
for both zones. Dashboard automation was unavailable. Managed protection was
therefore not enabled or verified during this change.

With dashboard or appropriately scoped API access, use AI Crawl Control to
block the selected AI crawlers. Restrict the resulting custom rule to the
intended hostname using an AND condition, especially for the shared
`night-zone.com` zone. Preserve existing rules. Do not enable a whole-zone
block on unrelated services. Keep ordinary search engines allowed. Verify
the saved rule and inspect Security Events; spoofed user-agent probes alone
cannot validate behavioral bot detection.

Official references:

- https://developers.cloudflare.com/ai-crawl-control/reference/bots/
- https://developers.cloudflare.com/ai-crawl-control/configuration/ai-crawl-control-with-waf/
- https://developers.cloudflare.com/bots/additional-configurations/block-ai-bots/
- https://developers.cloudflare.com/bots/additional-configurations/managed-robots-txt/

## Verification and deployment

```sh
node --test tests/crawler-policy.test.mjs tests/hosted-policy.test.mjs deploy/cloudflare-live/visitors.test.mjs
```

24 checks passed, including host isolation, browser/search compatibility,
robots readability, signup validation and inference/session budget enforcement.
Both Worker deployment dry runs passed. Static assets were unchanged.
The lab deployment used `--containers-rollout none`; no container rebuild or
restart was requested.

- Homepage Worker version: `3340d70c-18d9-4a63-8eae-39bb9d162a04`.
- Lab Worker version: `fcd2a6a0-de17-4502-bde3-e7c6cd4dc784`.

Post-deployment probes passed on both public domains: browser, Googlebot and
Bingbot user-agents returned 200; GPTBot, ClaudeBot, PerplexityBot and
OAI-SearchBot returned 403. Robots GET/HEAD remained accessible to GPTBot.
A GPTBot session-creation request was blocked before registration; an ordinary
visitor-status request returned 200. These probes created no sessions, visitor
records or model calls. Results and served robots files are retained privately
under `artifacts/crawler-policy-20260930/`.

Rollback: revert the crawler-policy imports/calls and restore the previous
homepage robots handler, then redeploy the Workers. No database migration or
secret changes are involved.
