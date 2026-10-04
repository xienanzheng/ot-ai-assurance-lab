# Recorded logs and context — 4 October 2026

## Water alarm benchmark: 1,000 locked cases

Open [test.cases.jsonl](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/test.cases.jsonl) for the 1,000 inputs, evidence mappings and labels. Each JSONL line is one complete record.

- [Fine-tuned Qwen4B responses](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/lr5e5-test.jsonl) and [summary](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/lr5e5-test-summary.json).
- [Base responses](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/base-test.jsonl) and [summary](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/base-test-summary.json).
- [Acceptance record](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/acceptance.json), [adapter selection](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/selection.json), manifest and source-binding identities.

The selected adapter achieved 995/1,000 valid responses, 477/500 full critical escalations, 631/1,000 supported assessments and 239/500 correct noncritical decisions, with two fabricated-reference errors. It did not qualify. This benchmark made no plant commands; a failed model criterion does not establish an executed unsafe action.

## Training and matched inference measurements

- Original candidates: [5e-5 training log](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/lr5e5/training.log), [1e-4 training log](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/lr1e4/training.log), adapter configurations, completion records and validation outputs.
- Matched original [base latency](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/base-latency.json) and [adapter latency](water-ot-ai-lab/artifacts/posttraining/water-alarms-v2/lr5e5-latency.json).
- [Later context/compact-choice pilot](water-ot-ai-lab/artifacts/posttraining/water-context-v3-pilot/): 160-case pool, matched 32-case local/cloud outputs, summaries, training logs/configurations and failures. These are development experiments. The two new adapters escalated every pilot case and remain unapproved.

The original matched warm median fell from 13.61 to 6.27 seconds. Shorter generated responses explain part of this reduction. It is not a controlled comparison against sub-two-second hosted inference.

## Shared 400-case comparison

[Comparison folder](shared-case-comparison/data/) contains the exact same 400 case IDs for Cloudflare Qwen30B, fine-tuned local Qwen4B and Jev, plus preserved collection/provenance records:

- [Cases](shared-case-comparison/data/valid.cases.jsonl).
- [Qwen30B](shared-case-comparison/data/cloud-responses.jsonl), [Qwen4B](shared-case-comparison/data/lr5e5-valid.jsonl), [Jev](shared-case-comparison/data/jev-responses.jsonl).
- [Comparison manifest](shared-case-comparison/data/comparison-manifest.json), [metrics](shared-case-comparison/data/comparison-metrics.csv), [representative failures](shared-case-comparison/data/representative-failures.csv).

These cases helped select the adapter. Jev receives code-defined choices and evidence assistance while Qwen generates proposals; this is a shared-case system comparison. The benchmark scorer function is frozen unchanged with its validation dependencies and SOP snapshot in `shared-case-comparison/source_snapshot/`. The private paper is not published.

## Independent audit and live integration

- [Gemma audit engineering records](decision-audit-20261002/): v7 development examples/results, separate holdout examples/results, local smoke/warm measurements and hosted Qwen/Jev exports. Small engineering tests, not a large model qualification benchmark.
- [4 October live water run](live-water-run-20261004/): session export, process-history CSV and run summary underlying the updated walkthrough. These observed trajectories are integration evidence, separate from the offline model comparison.
- [Retrieval check](water-ot-ai-lab/artifacts/retrieval-v2/evaluation.json): 18 relevance queries across the three simulated domains.

## SOPs and plant context

- [Context book](sop-context-current/docs/PLANT_CONTEXT_BOOK.md).
- [Structured SOPs](sop-context-current/services/supervisor/app/plant_sops.json).
- [Water alarm evaluation notes](sop-context-current/docs/WATER_ALARM_EVALUATION.md).
- [Independent audit design](sop-context-current/docs/DECISION_AUDIT.md).

The `sop-context-current` directory is a publication-date snapshot. Use the frozen comparison snapshot and benchmark manifest when reproducing historical scores; the current SOPs may have evolved.

## Verify without model calls

From the repository root, using Python with `pydantic>=2,<3`:

```sh
python research_Findings/Logs_2026-10-04/verify_evidence.py
```

The script re-scores saved outputs, checks paired case IDs, recalculates warm latency and compares the chart CSVs. `publication_manifest.json` preserves both original and published hashes. Local home paths were replaced in public text copies; model scores and numerical evidence were preserved. Original local artifacts remain untouched. No keys, signup database, adapter weights or private manuscript/manual are included.
