# V2 build ledger

Plan: docs/superpowers/plans/2026-10-24-modular-v2.md

- Isolated standalone Git repository created as requested; no V1 code imports or credentials copied.
- Task 1 complete: contracts/package suite 4 passed, after missing-module red run. Commit bb9e757.
- Task 2 complete: controller suite and contracts 18 passed. Lease expiry regression observed red then green. Commit 711676d.
- Task 3 complete: actual loopback asyncua server/client test; 19 total tests passed. Commit 407d68a.
- Task 4 implementation: 5 feedback tests passed; commit 3986ca3. Additional edge cases and overall review remain.
- Task 5 implementation underway: API tests passed; frontend built; isolated Compose build started.
- Ruling: implement a compact new disinfection/thermal bench rather than copying V1's full simulator. This keeps the initial integration exercise inspectable; it does not preserve V1's full process fidelity. Documented in plan before implementation.
- Ruling: use a standalone Git repository as the requested isolation boundary rather than a V1 worktree. No remote created.
- Ruling: use one versioned JSON snapshot inside a read-only OPC UA variable for the bundled simulator. This is an atomic envelope, not a generic vendor tag mapper. External tag mappings remain an explicit adapter milestone.
- Ruling: pin Vite 6.4.5 after npm audit reported a patched version. Original 6.3.6 build dependency is replaced before delivery.
- Current test warning: upstream Starlette TestClient uses a deprecated AnyIO BlockingPortal alias. No observed test failure; not suppressed.
- Independent whole-code review found six material defects; all were reproduced before fixes: scan failure/freshness, unresolved submission, stop-versus-arm race, outcome attribution, journal-error ownership cleanup, expired lease rearm.
- Added regression coverage for acknowledgement identity and cross-package context leakage. Suite now 36 passed, one upstream deprecation warning.
- Real browser smoke found pre-arm capture race; arm now invalidates capture and UI waits for new telemetry.
- Task 5 local API/build verified; live re-verification and final qualification underway.
- Real local Qwen smoke returned a valid but unsupported hold (17.8 s cold, including 10.1 s model load). Preserved as evidence, not counted as a correct model decision.
- Ruling: separate live sensor freshness (5 s) from maximum captured decision age (30 s for these noncritical test packages). Receiver revalidates current quality, protection, ownership and target, plus captured evidence valid at capture time. This permits normal cold inference without accepting arbitrarily stale proposals; requires site-specific qualification before any physical use.
- Fixed context contamination across reset generations and clarified conditional SOP versus active alarm facts in the prompt. No weight training or claim of model improvement.
- Task 5 complete: isolated Compose service, 1440px desktop and 390px mobile inspection, no horizontal overflow; runbook and modular extension guide written.
- Registry portability test adds a new cooling instance through data files without core edits. Six JSON contracts exported for adapter authors.
- Live cooling target accepted at 11°C; measured response reached its sustained objective after about 138 process seconds. Initial simultaneous restart failed because the app started before the receiver; failed evidence retained, bounded startup retry implemented, live rerun underway.
- Interrupted inference now becomes an explicit interrupted record on restart, rather than staying marked running. No replay is performed.
- Required audit smoke used actual local Qwen3:4b and Gemma3:4b. Qwen held without a justified wait; Gemma flagged it with a vague reason. These are not successful decision-quality trials.
- Independent critical-value check added: a clear alarm flag cannot authorise a measurement at or beyond the package's critical threshold.
- Current full suite: 51 passed, one upstream deprecation warning. Full real-time endurance remains a separate pending qualification category.
- Cooling live repeat passed all eight integration checks in 144.5 real seconds, including sustained outcome and disarmed restart; artifact cooling-runtime-1792905883.json. Water final run and real-time endurance follow separately.

- Duplicate asynchronous API job rejection and evidence export checked through the ASGI API. Latest suite: 52 passed.
- Water live response/restart run passed all nine checks in 120.1 real seconds, including stopping an active feedback loop across restart; artifact water-runtime-1792906071.json.
- Browser restart check reproduced a stale connection-error banner after successful recovery. Connection and operator-action errors now have separate state; final browser verification follows the rebuild.
- Final browser offline→online test passed: connection failure displayed and cleared automatically after recovery. Production frontend build passed.
- Delivery stays on local branch v2-local-bench in its own repository, as already requested. No public remote or V1 merge is appropriate for this standalone scope.
- 60-minute real-time fixture endurance started at 2026-10-25 05:31 UTC from clean source commit 0be2f9b. Browser navigated away; server feedback remained active and accepted the first target. Report: artifacts/endurance-1792906274.json. Result is pending; the process stops control when it finishes. Scoped caffeinate prevents idle sleep during this run only.

- Endurance completed: 3,600.04 real seconds, 12 fixture decisions, all eight checks passed, zero recorded errors.
- Local model review: 85 development/diagnostic calls completed; 4B focused interface 8/16 versus baseline 4/16; 8B 11/16, not promoted because latched-trip failures remain. Confirmation set unused. No weight training or V1/Cloudflare changes.
- Added attributed compact context, audit request/raw-response/latency exports, server-side review hash binding and fail-closed handling of audit request construction errors. Tests reproduced new failure before the fix.
- Gemma verdict accuracy improved to 12/16; only 6/16 explanations were materially supported in assistant review. Optional audit is not a safety guarantee.
- Final local build and 61 tests passed. Live evaluation-only export check passed six plumbing assertions, but Gemma falsely approved Qwen’s unjustified hold; recorded as a quality failure. Audit policy restored to off, control disarmed and feedback stopped.
