# Local agent team verification — 2026-09-09

- Installed qwen3:4b and five named profiles: water, nuclear, grid, safety review
  and consistency review. Workers use qwen3:8b; reviewers use qwen3:4b.
- All profiles request 16,384-token contexts. The native runtime reported a loaded
  reviewer context of 16,384. Profile configuration does not mutate the lab's
  globally configured scheduled model or context.
- A real grid worker produced audit `d8efc72a-3850-4932-8cff-14adc818266d`, including
  emitted reasoning and a captured-state gate result. The runner applied no controls.
- Initial reviewers returned inconsistent no-concern labels with nonempty findings.
  Validation rejected those reviews and retained the raw evidence. Prompt revisions
  made concern definitions and literal-quote requirements explicit. Initial attempts
  remain in the session archive; they were not overwritten.
- Both revised reviewers completed all four evidence batches of the same real
  worker record, with no validation errors in the final review session. A synthetic,
  clearly labeled contradiction/equal-treatment fixture elicited a cited
  reasoning/action inconsistency from the consistency reviewer. Quote checks passed.
  This tests the review workflow, not the reviewer's general accuracy or fairness.
- The offline regression suite passed 111 tests, with 3 opt-in integration tests
  skipped. Added tests cover local-only destinations, per-call worker overrides,
  context splitting with Unicode and complete source coverage, invalid citations,
  malformed output, truncation, persistence, and the absence of actuation requests.
- Simulation clocks and modes stayed paused/baseline during the script verification.

Sessions and full raw inputs/outputs are under `artifacts/agent-teams/`. Reports are
research observations. Valid quotations do not prove correct interpretation, and
model-emitted reasoning does not reveal guaranteed faithful internal computation.

Final real-trace review session:
`artifacts/agent-teams/20260909-052207-a99ec134/session.json`.
Both review reports are linked by that manifest; session status is `complete`.
