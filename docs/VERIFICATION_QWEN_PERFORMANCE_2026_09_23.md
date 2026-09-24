# Local Qwen fast-profile measurements

Measured on an Apple M4 with 24 GB unified memory, Ollama 0.33.3 and qwen3:4b on GPU. These are frozen-input proposal and gate evaluations, without simulator actuation. No weight training was performed. Hosted Qwen uses a different model; these timings do not describe it.

| Case | Standard | Fast | Observation |
|---|---:|---:|---|
| Water, fresh input | 27.098 s | 13.946 s | 48.5% shorter; fast proposal passed the gate |
| Grid, fresh input | 19.093 s | 12.524 s | 34.4% shorter; both shadow proposals |
| Water with history | 10.672 s | 21.807 s | Standard prompt evaluation was cached (0.054 s); not a fair uncached comparison |

Fast output was 98–109 tokens, versus 261–322 standard tokens. Fast requests constrain output to at most two actions and generate record identifiers server-side. They preserve gate sensor dependencies, abnormal sensor quality, current limits and protections; encode history without losing selected timeline values; and retain the uncompressed input in audit metadata. Independent gate validation is unchanged.

All six final calls completed. Standard water proposals were rejected; fast water proposals passed the gate. Passing is not evidence of better recovery, overall control accuracy or safe real-plant deployment. There is one measured pair per case, not a latency distribution or statistical performance guarantee. The history case still needs controlled cache testing.

Raw ignored artifacts: `artifacts/qwen-performance-fresh-2026-09-23/report.json`. Earlier reports are exploratory and superseded for performance comparisons. No public simulator deployment was performed for these changes.
