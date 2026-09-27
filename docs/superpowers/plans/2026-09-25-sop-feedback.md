# SOP Feedback Implementation Plan

**Goal:** SOP-informed, bounded, delay-aware feedback for both providers, with measurable offline post-training experiments.
**Spec:** ../specs/2026-09-25-sop-feedback-design.md
**Execution:** Native in this session, as authorized by the user's request to plan and execute.

- [ ] Create typed SOP registry and response profiles, grounded in simulator code. Test bad-quality/missing inputs, domain isolation, hashes, first-order settling calculations and ambiguous response observations.
- [ ] Share SOP/timeline context across Qwen and Jev; add optional local cross-encoder reranking with explicit deterministic fallback. Audit selected sources and timing. Test both adapters and context preservation under fast profile.
- [ ] Add temporal gate and bounded lease parameter at domain endpoints. Test early repeat/reversal, conflicting changes, critical escalation, and lease restoration.
- [ ] Implement backend feedback state machine: start, sample, decide, wait, stop. Serialize writer ownership, enforce call budgets, simulation-time waits, reset detection and cancellation before submission. Test using fake clocks and real domain gates.
- [ ] Add compact feedback controls/status and explanations to AI decisions. Check desktop, phone, keyboard, exports and manual override interaction.
- [ ] Generate provenance-labelled train/validation/test cases with disjoint episode seeds. Train a small retrieval reranker and an experimental Qwen LoRA adapter if supported locally; evaluate before/after on held-out examples. Do not promote without measured evidence. Export trajectory-based preference candidates, retaining rejected/unsafe outcomes separately.
- [ ] Run deterministic tests, offline evaluations and live local provider loops. Update README/manual-facing docs with implemented behavior and measured limits. Build/deploy only verified simulator changes and push source; keep trained artifacts local.

## Constraints and review focus

No physical equipment access; independent process gate remains authoritative. SOPs describe this simulator, not operational procedures. Existing hosted limits remain 10 calls/session, 200/day, 10 seconds between calls; failed calls count. Loop call budgets cannot override edge quotas. Model outputs, probability and acceptance are not evidence of successful recovery. No automatic training on visitor records. Optional dependencies stay out of hosted image. Paused plants do not trigger repeated inference. An in-flight response after stop/reset cannot actuate. Slow-response windows must not outlive their control lease. No datasets/credentials/private material in git.

## Execution update — 26 September 2026

Implemented the typed SOP book, shared provider context, temporal gate, adaptive feedback leases, serialized start/stop/application, bounded observation history, delayed outcome scheduling, and frontend feedback controls. Local browser checks cover desktop and phone. Real-grid-gate tests cover both provider paths using controlled proposals. A live Jev loop completed two hold decisions; a separate local Qwen retest also completed two holds and a budget stop after training finished.

Completed 24-step and 120-step local Qwen LoRA pilots with recorded evaluations. The longer adapter reached 8/12 on fresh curriculum cases but only 2/6 on unseen critical-alarm overrides: **not promoted**. See `docs/POSTTRAINING_RESULTS.md`. BERT reranker training, trajectory preference export, RL and production promotion remain unfinished. No claim of full operational model validation or public deployment is made.
