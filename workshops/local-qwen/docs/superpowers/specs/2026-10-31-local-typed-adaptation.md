# Local typed Qwen adaptation — design and experiment specification

## Purpose
Improve useful, fast local decisions in the standalone V2 water/cooling bench through a real, bounded supervised LoRA experiment. Previous free-form adapters collapsed toward escalate or adjust; current V2 still makes hold errors and inaccurate explanations. Test a smaller typed decision task before adding RL. The experiment remains offline/shadow research and does not replace the working demo.

## Design
A shared typed interface takes the existing V2 `decision_view` (safety flags, sensor prerequisites, targets, objective, observation window, coherent trend and command limits). It offers immutable code-authored proposals labelled with single uppercase letters: three hold reasons, three escalation reasons, then up to four feasible numerical targets. Qwen selects one label using its next-token logits. Code decodes that label into the existing Proposal contract. No choice is removed because a ground-truth label says it is wrong. Invalid selections remain failures; no automatic fallback command.

This is a system-assisted typed decision classifier, not free-form model diagnosis. Structure, reference names, target menu and concise explanation templates come from code. Report label/status/target correctness and supported reason separately. Relative choice probabilities are not calibrated safety confidence. Compare base and adapter with identical inputs, logits scoring, runtime and candidate menus; never credit shorter typed inference to weight training.

## Binding constraints
- Work only in the isolated V2 experiment worktree; V1, Cloudflare, the running demo, prior checkpoints and prior experiment artifacts remain unchanged.
- Use only simulated package states; no visitor data, real plant connection, hosted inference or automatic actuation.
- Use pinned local Qwen3-4B-4bit snapshot `4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25`; no network downloads or dependency upgrades.
- Use exactly the same chat template with `enable_thinking=False` for training and evaluation; assert full/prompt token prefix identity. Mask prompt loss. Reject overlength examples; never truncate protection evidence.
- Freeze 384 training, 48 validation and 96 test cases before model calls; each has a unique episode ID, disjoint numeric/state fingerprints across splits, balanced statuses and equal water/cooling counts. Training uses seed 3101, validation 3102, test 3103. Test includes combined faults and misleading SOP prose not present in training.
- One LoRA run: four trainable layers, rank eight, batch one, LR 5e-5, gradient checkpointing, seed 42, maximum 128 updates, checkpoints at 64 and 128, maximum sequence 4096. No online RL, DPO run or iterative training on the locked test.
- Choose checkpoint using validation only, ordered by protection/prerequisite misses (fewer), correct supported decisions (more), correct status/target (more), then lower step. Evaluate the selected candidate and base on the locked test exactly once each. Preserve errors and denominators; do not retry wrong outputs.
- Runtime comparison uses greedy one-forward-pass candidate logits, exact single-token labels, sequential warm calls with no concurrent GPU training or Ollama inference. Save per-case latency and token counts, median and p95. Separate warm-up and load time.
- A positive research readiness result requires zero protection/prerequisite misses; >=90% correct status/target overall; >=90% supported reason codes; >=90% correct holds; >=4 additional correct test cases versus base; and both median and p95 latency <=1.10 times matched base. Otherwise retain the candidate offline. Passing is not a safety certification and never enables actuation automatically.
- Preserve all raw scores, labels, decoded proposals, manifests, source/model hashes, test evidence and failed candidates. Never represent a deterministic check or template as model reasoning.

## Policy before training
Use the current reactive SOP consistently: protection overrides everything; bad/stale/missing/unit-inconsistent sensors or absent flow require escalation; active wait requires hold; in-band measurement requires hold even if target is outside; outside-band reading with a strictly interior target and a demonstrated coherent approaching trend requires hold. Otherwise use a corrective feasible target; no directional headroom requires escalation. Preventive in-band adjustment is deliberately not taught in this experiment. Do not change old benchmark labels.

## Tests and evidence
Unit tests exercise policy priority, both correction directions, finite recovery versus intermediate step, waits, stale telemetry, bad units, same-generation trends, exhausted headroom, wrong reason despite correct disposition, invalid labels, immutable output records, split leakage, token prefix consistency and artifact collision/hash checks. Include perturbation pairs where only protection, wait or trend changes. Never score JSON validity as learned competence because decoding supplies the structure.

New case labels derive from explicit bench SOP rules in a separate oracle, not the production proposal-findings function. Fixed hand-written edge cases test the oracle independently. The experiment does not establish generalization to new physical plants; both benches are simple direct-target first-order systems.

## Research basis and applicability
- QLoRA (Dettmers et al., 2023), https://arxiv.org/abs/2305.14314 — frozen quantized base plus low-rank updates motivates the memory-efficient local experiment. MLX uses its own quantization; do not claim this reproduces NF4/paged optimizers.
- Outcome Rewards Do Not Guarantee Verifiable or Causally Important Reasoning (Yu et al., ICML 2026), https://proceedings.mlr.press/v306/yu26av.html — separate outcome correctness from supported explanations. We do not implement their CIR/SR metrics or claim causal access to hidden reasoning.
- Direct Preference Optimization (Rafailov et al.), https://arxiv.org/abs/2305.18290 — a future preference-training option once preferences and evidence are calibrated; not a claim that DPO is run here.
- MLX-LM LoRA documentation, https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md — prompt masking, local quantized fine-tuning, adapters; inspect installed APIs rather than upgrading to main.

## Review and scope
Use independent subagent task reviews and a final broad review, then the actual Claude critique bridge with fixed rubric and at most three judge calls. Repair reviewed code defects with scoped re-review. A failed model test is a result, not a reason to reuse the locked test for more training. Report any unavailable capability or resource error honestly. No automatic active-provider promotion or deployment is part of this iteration.

## Authorized teacher addendum
After implementation began, the user authorized paid Claude teacher calls. A separate simulated training-only scenario workshop may call the official Anthropic API with the locally stored credential. This does not change the frozen experiment inputs, labels, single training run, checkpoint selection or locked test. Teacher suggestions are untrusted curriculum drafts; record source and validate them against explicit SOP policy before future use. No real plant, visitor data, source secrets or held-out test cases are sent. The local baseline/adaptation experiment still uses no hosted inference.
