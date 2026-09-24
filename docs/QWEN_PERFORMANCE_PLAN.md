# Qwen response-time plan

Objective: reduce local end-to-end decision time while preserving current observations, permitted controls and independent gate enforcement. Model customization means task-specific context and output contracts here; no weight fine-tuning is claimed.

1. Measure prompt evaluation, output generation, load time, retrieval and full request latency separately. Prior water calls spent about 22–25 seconds processing prompts and 16–27 seconds generating output. Loading was only milliseconds, so warming alone cannot fix this.
2. Keep a standard research profile and add an explicit fast supervisory profile. Disable optional thinking for fast calls; preserve it as a separate research option.
3. Remove model-generated server fields (UUID/timestamp/source) from the requested output schema. Require a sparse list of at most two actions, validated and converted server-side to the existing gate proposal. The server still supplies provenance and IDs.
4. Compact repeated timeline observations losslessly using columns and constant values. Preserve all water gate sensor dependencies, all bounded process readings, every non-good-quality sensor, all current constraints, permissives, trips and authority boundaries. Exclude normal auxiliary telemetry and PID internals from the fast prompt, with the full uncompressed context retained in audit storage. Keep full original context in audit storage.
5. Use contextual BM25 retrieval for this nine-record corpus; compare with local hybrid and the one-off OpenAI embedding evaluation. Add only two short relevant records, retaining full source metadata in the audit.
6. Run paired frozen-state benchmarks with identical model and physical inputs, standard versus fast. Report schema failures, gate outcomes, token counts and timing; never substitute a cached action for a fresh state decision.
7. Keep profile selection visible. Do not enable autonomous control based solely on a latency win. Longer scenario testing remains necessary to establish recovery performance.
