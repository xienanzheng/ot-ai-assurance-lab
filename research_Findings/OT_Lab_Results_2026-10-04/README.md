# OT Lab results - 4 October 2026

Open `output/pdf/OT_Lab_Results_2026-10-04.pdf` for the eight-page chart collection.
Individual charts are in `figures/` (320-dpi PNG and editable SVG), with vector PDF in `output/pdf/`.
This chart collection and its supporting research records are published in `research_Findings/`. Publication does not deploy or change the simulator.

## What is supported

- Original 160-update Qwen4B adapter: warm median 13.61 -> 6.27 seconds (54.0% reduction); p95 17.81 -> 6.74 seconds (62.2% reduction).
- Assisted 80-update pilot: median 10.28 -> 7.68 seconds (25.4% reduction); p95 13.12 -> 8.38 seconds (36.1% reduction).
- Compact 80-update pilot: median 6.49 -> 6.20 seconds (4.5% reduction); p95 7.26 -> 6.42 seconds (11.7% reduction).
- All latency comparisons are matched only within their experiment. Each has 32 sequential cases and excludes the first response (31 warm).
- Original speed improvements coincide with much shorter generated responses. The records do not isolate decoding throughput; `output_tokens / total_seconds` would not be a valid decoding tokens/second benchmark.
- The p95 index conventions differ across the original and pilot studies; we preserve each original convention, recorded in the manifest. Small samples make tail estimates imprecise.
- Shared-case model quality uses 400 development cases, not held-out evidence. Jev's code-defined options and evidence assistance differ from Qwen's generative interface.
- The original adapter failed its 1,000-case locked test. Both later adapters escalated every pilot case and remain unapproved.
- Training-loss checkpoints use only four validation examples; lower loss does not prove better control.
- Retrieval is a small 18-query relevance check, not a control-performance evaluation.

## Files

01: matched inference time; 02: response length/time; 03: training loss;
04: three-system category results; 05: locked acceptance; 06: later pilot decision quality;
07: retrieval; 08: structured validity vs correctness.

CSV tables, per-case scores, recomputed metrics and source SHA-256 manifest are in `data/`.
Bundled case records, raw model outputs, training logs and versioned SOP context are in [Logs_2026-10-04](../Logs_2026-10-04/README.md). Original local evidence and the private paper remain unchanged.

## Rebuild

From the repository root:

```sh
python research_Findings/Logs_2026-10-04/verify_evidence.py
python research_Findings/OT_Lab_Results_2026-10-04/scripts/build_charts.py
```

Uses the bundled frozen scorer and saved records. Install `pydantic>=2,<3`, `numpy`, and `matplotlib` in an isolated Python environment. No inference or training occurs. Rebuilding uses DejaVu Sans when the original local IBM Plex font files are unavailable; the published charts retain their original typography. The source manifest preserves the original hashes; the publication manifest records the public copies and local-path redactions.

## Other data available for future figures

- Actual sensor trajectories, PLC targets, gate outcomes and chemical consumption from saved water exercises.
- Model confidence, proposal contents, provider usage and failure categories from decision exports. Confidence is not calibrated correctness.
- Audit verdicts, response time and evidence references from the small Gemma engineering review set.
- Timing and usage from hosted runs, to be shown separately from matched local speed measurements.

No recorded power/energy benchmark, broad physical-plant validation or measured field operating savings exists in this pack.
