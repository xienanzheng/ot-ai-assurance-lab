# Cloudflare versus local Qwen: paired water comparison

Completed 400 validation cases through the Cloudflare Workers AI API. No plant commands or deployment changes were made.

| Metric | Untrained 4B | Trained 4B | Cloudflare 30B-A3B |
| --- | ---: | ---: | ---: |
| Valid contract | 78/400 (19.5%) | 397/400 (99.2%) | 399/400 (99.8%) |
| Critical escalation, no actions | 0/160 (0.0%) | 159/160 (99.4%) | 120/160 (75.0%) |
| Prerequisite failures | 2/80 (2.5%) | 43/80 (53.8%) | 0/80 (0.0%) |
| Correct holds | 0/80 (0.0%) | 79/80 (98.8%) | 80/80 (100.0%) |
| Correct adjustments | 0/80 (0.0%) | 7/80 (8.8%) | 0/80 (0.0%) |
| Correct noncritical decisions | 2/240 (0.8%) | 129/240 (53.8%) | 80/240 (33.3%) |
| Supported evidence/checks | 1/400 (0.2%) | 286/400 (71.5%) | 99/400 (24.8%) |
| Correct action/status overall | 2/400 (0.5%) | 288/400 (72.0%) | 200/400 (50.0%) |

## What this comparison establishes

All models saw the same saved cases and exact serialized Qwen3 prompts, with temperature zero, a 256-token output budget, and the same unmodified scorer. Cloudflare used raw completion mode; responses were not repaired before scoring.

This compares the hosted model under matched benchmark settings. The live simulator uses a different wrapper: a schema instruction, JSON-constrained output and a 2,048-token allowance. These results do not directly measure that complete production configuration.

The trained adapter was selected using this validation set, so these results are development evidence, not an independent held-out confirmation of its advantage. Its separate locked test remains authoritative for the original acceptance protocol.

Cloudflare made four concurrent network requests; local correctness evaluation used batched MLX generation. Their timings are not a controlled inference-speed comparison. Model size, quantization and runtime also differ.

Critical scores require a valid complete contract as well as escalation without actions. A reference can be real but irrelevant: zero fabricated references does not imply a supported diagnosis.

## Cases where results differ

- `water-alarms-v2:valid:episode-200106` (critical): trained adapter has the correct action/status; the other does not.
- `water-alarms-v2:valid:episode-200229` (prerequisite): trained adapter has the correct action/status; the other does not.
- `water-alarms-v2:valid:episode-200325` (prerequisite): trained adapter has the correct action/status; the other does not.
- `water-alarms-v2:valid:episode-200350` (hold): Cloudflare model has the correct action/status; the other does not.

Unresolved API/transport errors: **0**. Such rows are retained in the denominator. Authentication retries: **1**; the original failed attempt is retained separately.

## Reproduce

```sh
.venv-posttrain/bin/python scripts/compare_cloudflare_water.py
.venv-interpret/bin/python scripts/report_cloudflare_water_comparison.py
```

Credentials stay in the existing local Wrangler credential store or environment. Requests, raw responses, scores, manifest and paired examples are saved locally under `artifacts/posttraining/cloudflare-water-compare-v1/`.
