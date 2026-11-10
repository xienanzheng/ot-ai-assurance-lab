# Local Typed Qwen Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train and evaluate a local Qwen3-4B adapter on V2 typed control decisions with reproducible accuracy, evidence and latency results.

**Architecture:** A shared offline interface converts captured V2 context into bounded code-authored options; the model selects a label and code decodes its existing Proposal. A separately tested SOP oracle creates a frozen balanced curriculum. MLX trains a small adapter and compares it with the same pinned base without applying commands.

**Tech Stack:** Python/Pydantic/pytest, existing MLX-LM 0.31.3 and MLX 0.32.2, local quantized Qwen3-4B cache.

**Spec:** `docs/superpowers/specs/2026-10-31-local-typed-adaptation.md`

## Global Constraints

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

## Review Focus

- A healthy-looking sensor plus a trip must escalate; Task 1 tests conflicting evidence priority.
- Correct hold disposition with the wrong reason must not receive supported-evidence credit; Task 1 tests reason/status separately.
- Shortened or mismatched chat templates can train on different prefixes; Task 2 fails before training and tests the tokenizer contract.
- Reused output directories or changed frozen datasets can invalidate selection; Task 2 rejects collisions and hash drift.
- Fast but always-hold/escalate policies can look good; Task 3 reports per-class counts and predeclared readiness including hold performance.

## File responsibilities

`training/typed_policy.py`: common typed inputs/options/decoding, no model loading.
`training/bench_cases.py`: independent SOP oracle, fresh case generation, hashes, scoring.
`training/mlx_experiment.py`: local MLX tokenization/training/evaluation and checkpoint selection.
`scripts/run_typed_training.py`: command entry point and bounded stage orchestration.
`tests/test_typed_policy.py`, `tests/test_bench_cases.py`, `tests/test_mlx_experiment.py`: CPU checks and fake-tokenizer edge cases; optional actual tokenizer preflight separately.
`docs/TYPED_QWEN_EXPERIMENT.md`: measured report, sources, limitations and reproduction commands.

### Task 1: Typed policy and independently labelled frozen cases

**Files:** Create `training/__init__.py`, `training/typed_policy.py`, `training/bench_cases.py`, `tests/test_typed_policy.py`, `tests/test_bench_cases.py`.

**Interfaces:**
- Consumes `v2.decision_context.decision_view(context: dict) -> dict`, `v2.packages.load_package(name)`, existing `Proposal` and `Snapshot` contracts.
- Produces `make_options(context: dict) -> dict[str, dict]`, `messages_for(context: dict) -> list[dict]`, `decode_choice(context: dict, label: str) -> Proposal`.
- Option keys A/B/C = hold in-band/wait/settling; D/E/F = escalate protection/prerequisite/no-headroom; G/H/I/J map in order to available existing candidate targets. Include all six non-actuation choices for every state. Do not filter labels using expected answers. Option dictionaries include reason_code and proposal. Rationale templates and references are attributed to code.
- Produces `generate_cases() -> dict[str,list[dict]]`, `freeze_dataset(output: Path) -> dict`, `oracle(context: dict) -> dict`, `score(case: dict, label: str, proposal: Proposal|None) -> dict`.
- Case keys: id, episode_id, split, domain, scenario, context, expected. Expected keys: status, reason_code, acceptable_targets, protection_required. Reason codes correspond to the six named hold/escalate types plus `adjust`. All target numbers are from the captured candidate menu. `score` returns decision_correct, supported_reason, protection_miss, error; wrong reason and wrong numeric choice are distinct.

- [ ] Step 1: Write failing tests for `test_protection_overrides_normal_reading`, `test_wait_overrides_adjustment`, `test_in_band_outside_target_holds`, `test_settling_needs_coherent_trend`, `test_both_correction_directions`, `test_no_headroom_escalates`, `test_correct_status_wrong_reason_is_unsupported`, and `test_invalid_choice_never_falls_back`. Assert decoded outputs do not mutate input/options; unrelated SOP prose cannot change the oracle.
- [ ] Step 2: Run the two new test files and record expected import/behavior failures.
- [ ] Step 3: Implement interfaces. Build messages from existing decision_view plus options, with a concise explicit SOP priority and untrusted-data instruction. No scenario names, expected fields, split names or labels from the oracle in the prompt. Keep live protection, age/quality failures, waits, target, bounds and trend. Oracle must not call production `proposal_findings` or use a model verdict. Generate the specified counts with independent seeds, unique episodes and nonduplicate state fingerprints; hold/adjust/escalate each exactly one third per split, equal domains. Include stale/bad/unit/no-flow, conflict trip, upper/lower, in-band, waiting, settling and exhausted authority. Test-only combinations/prose are not trained. Use canonical hashed manifest and refuse overwrite.
- [ ] Step 4: Add tests asserting exact split sizes/status/domain balance, pairwise disjoint episodes and fingerprints, deterministic regeneration, manifest tamper detection interface if provided, and known hand-written edge labels. Run focused tests then the full existing suite.
- [ ] Step 5: Commit this task and write report with RED/GREEN evidence. Do not run model inference or train yet.

### Task 2: Matched MLX training and evaluation pipeline

**Files:** Create `training/mlx_experiment.py`, `scripts/run_typed_training.py`, `tests/test_mlx_experiment.py`.

**Interfaces:**
- Consume Task 1 functions and saved cases without changing their contract.
- Produce `tokenize_example(tokenizer, messages: list[dict], label: str, max_length: int=4096) -> dict` with prompt_tokens, full_tokens, prompt_length; shared `enable_thinking=False`, verified prefix, single-token choice IDs and no truncation.
- Produce a CLI `python -m scripts.run_typed_training --stage prepare|baseline|train|validate|test|report --root PATH --model PATH` using lazily imported installed MLX APIs. Root is new per experiment. Store hashes of source, dataset, model/tokenizer, versions and settings before inference. `prepare` writes chat JSONL train/valid and freezes context/messages/options with cases. Test data stays outside the training loader's directory.
- Baseline evaluates validation before training. Train once to 128 steps and preserves both 64/128 checkpoints. Validate both separately; selection file is written and hash-bound before any test inference. Test evaluates base and selected checkpoint once each, with identical ordered cases and separate warm-ups; no fallback predictions or outcome retries. Report writes JSON summary and case failures.

- [ ] Step 1: Write failing CPU tests for exact template/prefix match, overlength rejection, non-single-token labels rejection, unknown labels, changed manifest rejection, output collision, validation-only selection ordering/ties, and per-class summaries with unavailable outputs retained. Include always-hold and always-escalate cases failing readiness. Tests must exercise production helpers and must not require GPU.
- [ ] Step 2: Run focused tests, record failure evidence.
- [ ] Step 3: Implement bounded training/evaluation using installed MLX code; reference V1 `scripts/train_water_alarm_adapter.py` read-only for the corrected chat-template handling. Use response-only loss on the selected label. Score all supplied option labels from the final prompt token logits in one forward pass; no oracle-driven class masking or free-form decode. Log raw logits/relative probabilities and decoded proposal with attribution. Distinguish wall time, prefill/token counts, load and warm-up. Context cap 4096; enforce documented 128-step configuration. Do not modify global environments, unload other users' models, or run GPU work in this task.
- [ ] Step 4: Run focused tests then full CPU suite and compilation. Document exact commands plus installed dependencies required. Reject test before selection, and dataset/source drift between selection and test. Tests and pipeline must not touch old experiment paths.
- [ ] Step 5: Commit and report RED/GREEN evidence and how the controller should run the stages sequentially.

### Task 3: Run the bounded local experiment and publish an honest local report

**Files:** Create `docs/TYPED_QWEN_EXPERIMENT.md`; modify README with report link. Runtime artifacts only in ignored `artifacts/typed-qwen-2026-10-31/` in this worktree.

**Interfaces:** Consume Task 2 CLI and reports. No runtime/app/provider changes or automatic deployment. Use existing `/Users/xienanzheng/Desktop/Berkeley/School/Sem 3 MIMS/M3 Fellowship/water-ot-ai-lab/.venv-posttrain/bin/python` and cached base path supplied by controller. Reuse dependencies read-only; execute from this worktree.

- [ ] Step 1: Verify local resources and no active inference/training conflicts. Record hardware, versions and model digest. Use a process-scoped keep-awake wrapper, no power-setting changes. Check token lengths and prefix invariants before starting costly work.
- [ ] Step 2: Run prepare and matched baseline; then the single bounded training run, validate the two frozen checkpoints, select using validation only, and evaluate locked test base/candidate once. Preserve partial/error evidence and stop model execution on resource error rather than rerunning until success. Do not revise prompts or labels after test results. Report progress and stage commands to controller.
- [ ] Step 3: Recompute report values from saved rows. Report counts/denominators for class decisions, supported reasons, critical/prerequisite misses, median/p95 and output/token budgets. Distinguish faster typed interface from any adapter quality benefit. Include unsuccessful cases and all acceptance criteria; state candidate remains offline regardless of outcome.
- [ ] Step 4: Produce the report with research sources and limits (small simulated set, rule-authored teaching, template-generated explanations, simple process family). Include reproduction commands and precise adapter path, base digest, data hashes and selection evidence. Report whether actual weight updates occurred. No claims of general safety, best-model status, hidden-thought access or Cloudflare fine-tuning.
- [ ] Step 5: Run relevant CPU regression checks if code changed; otherwise rely on existing test evidence and verify report arithmetic. Commit documentation, leave artifacts private, and report completion/failures for independent final review.
