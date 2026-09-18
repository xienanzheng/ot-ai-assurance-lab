# Interpretability dashboard implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task.

**Goal:** Present traceable control risks and measured local-model activation experiments.
**Architecture:** Offline Python experiments → versioned artifacts → local static catalogue → React research workspace.
**Tech Stack:** Transformers, PyTorch, NNsight, NumPy, Matplotlib, existing React/Vite.
**Spec:** docs/superpowers/specs/2026-09-11-interpretability-dashboard.md

## Global constraints

- One local model, short contexts, no actuation from interpretability scripts.
- Keep historical 8B control data distinct from new 4B activation experiments.
- Show counts and measured effects, never invented failure probabilities.
- Preserve failed trials and all raw evidence. No publishing or uploading.

## Task 1: Evidence calculations and export

Files: scripts/research_evidence.py, tests/test_research_evidence.py.
Interfaces: summarize_control(session) -> dict; export_catalogue(root, output).
- [x] Test a failed proposal is excluded from applied count and included in failures.
- [x] Test excursion denominators exclude minute zero and use matched horizons.
- [x] Test absent gate/response/empty samples yield unknown values rather than success.
- [x] Run `python3 -m unittest tests.test_research_evidence`; implement and rerun.
- [x] Export preserved control evidence with source hashes and provenance.

## Task 2: Instrumented experiment

Files: scripts/run_mechanistic_probe.py, tests/test_mechanistic_probe.py,
requirements-interpretability.txt.
Interfaces: matched_prompts(low, high, swapped), patch_last_position(output, source),
run output results.json plus activations.npz and plots.
- [x] Test prompts differ only in the selected numeric value, decision mapping swaps.
- [x] Test a patch changes exactly the selected last-position vector, retains dtype,
  and rejects incompatible shape; use tiny real tensors.
- [x] Capture actual Qwen3 4B activations with Transformers and NNsight.
- [x] Run three paired values, both mappings, selected layer patches and no-op controls.
- [x] Record raw/conditional token scores and disclose low choice mass.

## Task 3: Interactive dashboard

Files: services/web/src/ResearchDashboard.jsx, research.css, research-main.jsx,
services/web/research.html; modify App.jsx and vite.config.js.
- [x] Load the catalogue, handle loading/error/empty states and exports.
- [x] Link time scrubber, threshold sensitivity, evidence rows and decision detail.
- [x] Add experiment selector, activation heatmap and signed patch-effect view.
- [x] Build using `npm run build`; inspect desktop and mobile with agent-browser.

## Task 4: Verify and document

- [x] Run relevant Python tests, real-model controls and frontend build.
- [x] Review data provenance, labels and scientific interpretation.
- [x] Document commands, local dashboard URL, measured findings and limitations.
