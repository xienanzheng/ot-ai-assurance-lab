# Decision evidence and mechanistic interpretability

The user has requested implementation of a dashboard and real local mechanistic
interpretability experiments. Extend the existing research workspace. Audience:
a fellowship presentation in a dim lecture room, followed by individual evidence
review. Retain the lab's dark teal product palette, readable chart labels and
keyboard-accessible controls.

## Deliverables

1. Archived decision timeline: sensor series, proposals, gates, actual target and
   dosing feedback, failures, raw emitted reasoning and JSON download. The first
   dataset is the 60-minute failed recovery trial; never rewrite it as a success.
2. Risk evidence: observed excursion minutes, proposal failures, measured latency,
   lease expiry and context coverage. Sensitivity thresholds affect display only.
   No invented disaster probabilities, casualty predictions or alignment scores.
3. Mechanistic experiment: cached Qwen3 4B loaded through Transformers/PyTorch,
   with NNsight activation capture. Matched short prompts differ only in one
   water-quality value; repeat three value pairs and swap A/B decision labels.
   Capture layer responses, patch selected last-position residual activations in
   both directions, and include same-input patch controls. No actuation authority.
4. Explicit provenance: model revision, dtype, device, package versions, prompts,
   token IDs, raw activation files and metrics. Distinguish Qwen3 4B instrumented
   classification experiments from historical Qwen3 8B quantized control trials.

Activation norms are descriptive; patch effects test a specified intervention.
Neither is a calibrated risk probability or complete extraction of latent thoughts.
Restrict the initial experiment to short sequences and one model in memory. Record
all attempted cases and errors. A zero or unexpected effect is a valid result.

## Architecture

Python scripts produce local JSON/NPZ artifacts. A deterministic exporter builds a
local read-only research catalogue under services/web/public/research. React loads
that catalogue through the existing lab tab and a standalone research.html entry.
No browser inference, external upload or control API writes from this dashboard.

## Verification

Test risk denominators, unavailable outcomes, matched horizons and patch alignment.
Verify no-op patch equivalence and NNsight/PyTorch capture agreement on real tensors.
Run the real 4B experiment, frontend build and browser checks at desktop/mobile.
