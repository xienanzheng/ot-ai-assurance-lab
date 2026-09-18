# Evidence and risk dashboard

Double-click **Start Research Demo.command** in the project folder to open the built demo at **http://127.0.0.1:18774/research.html**. Keep its Terminal window open during the presentation; Ctrl+C stops it. The development server remains available at **http://127.0.0.1:18773/research.html** when Vite is running. The same workspace is available from **Evidence & risk** in the main control room. It reads saved local artifacts and works without Docker or a live plant connection.

## Present the product in five minutes

The dashboard now opens on **Demo**. Select **Present** to hide the research navigation and expand the content for projection. Arrow keys on the chapter heading advance or return; Escape leaves presentation view. Buttons and sliders keep their normal keyboard behavior. Speaker notes are optional and are visible on the same screen, so hide them before sharing the audience display.

1. **System — 45 seconds.** Explain the boundary: sensors and context → local AI proposal → deterministic gate → PLC and simulated plant. The wider lab has water, nuclear and grid workspaces; this saved evidence is from water.
2. **Disturbance — 60 seconds.** Play the archived timeline, or jump to the first excursion. Playback runs at two simulated minutes per second. It stops at the end and pauses when the browser tab is hidden. The original model calls were much slower and paused the simulation.
3. **Control — 60 seconds.** Compare the target, delivered dose and effluent across consecutive readings. The target appears at minute 55; the dose response is visible at minute 56. Open the exact exchange if the audience asks for context or reasoning text.
4. **Internals — 90 seconds.** Explain that this is a different 4B model on a binary threshold task. At layer 18, show the small recorded effect. At layer 30, show the activation swap reversing the A/B preference, then restore the original. Change the paired case to reverse the labels. Read conditional probability together with A/B token mass.
5. **Findings — 45 seconds.** Compare the failed dynamic control run with the successful narrow classification task. Download the evidence brief. Ask what additional evidence would justify bounded control authority.

The swap button displays measured results from the saved experiment; it does not run fresh inference. Detailed timeline, risk and internals views remain accessible from the demo. The exported Markdown brief includes study IDs and source checksums.

The launcher serves the built static files on loopback only and requires Python 3. It does not need Docker, Ollama, Node or model weights at presentation time. After editing code or exporting new evidence, rebuild before launching:

```bash
python3 scripts/research_evidence.py
npm run build --prefix services/web
python3 scripts/serve_research_demo.py
```

## Detailed evidence walkthrough

1. **Decision timeline:** begin at minute 0, then jump to minute 30. The simulated effluent crosses the illustrative 1.0 NTU bound. Open the failed exchange, its emitted reasoning, and its exact sensor/history context. The model used an output budget without producing a valid control proposal.
2. Jump to minute 54, the one applied proposal. Compare the proposed coagulant target with the actual delivered dose. Move to minute 56 and then 60 to see the process response and lease expiry. A gate acceptance did not produce recovery.
3. **Risk evidence:** compare the baseline and AI trajectories. Move the display threshold; it changes the analysis only. Read inference failures, elapsed inference time and final effluent separately. The simulator clock paused during inference, so this does not establish real-time control capability.
4. **Model internals:** explain the change of model and task before showing the heatmap. This is a new Qwen3 4B classification experiment, separate from the historical Ollama 8B controller. Switch to a case with reversed A/B labels. Inspect a late-layer cell, then the intervention table and verification records.
5. End with the evidence boundary: the model can identify a simple threshold crossing, yet the earlier control agent did not resolve the dynamic process problem. These are different capabilities. Neither experiment estimates a city's accident probability or proves alignment.

## What was measured

### Historical control evidence

The preserved complete run is `artifacts/recovery-timelines/20260910-185511-0ae02a4f/session.json`. An interrupted attempt remains selectable too.

- Eight model exchanges: seven failed; one was applied.
- Both arms ended at approximately 1.229 NTU, above the illustrative 1.0 NTU bound.
- Both had 31 above-bound observations among 60 good-quality post-step observations. Minute zero is excluded from this count.
- Holding each measurement constant until the next sample estimates 30 minutes above the bound in the common 0–60 minute window. This is a different metric from the 31 observed endpoints; neither implies continuous measurement between samples.
- Bad-quality or missing readings are excluded from observed coverage. Their absence is not counted as safe operation.

Legacy exporter fields ending in `_minutes` retain post-step counts only for verified one-minute cadence. New `_samples` fields and `sample_count_method` describe counts explicitly. Use the dashboard's separately labelled duration calculation for estimated elapsed exposure.

### New mechanistic experiment

Results: `artifacts/mechanistic/20260912-010135-a5b1d398/`.

- Model: `Qwen/Qwen3-4B`, revision `1cfa9a7208912126459214e8b04321603b3df60c`, float16, Apple MPS. Weights were already cached locally.
- Libraries: Transformers 4.57.6, PyTorch 2.14.0, NNsight 0.7.0, NumPy 2.5.3; Matplotlib provides standalone figures. Exact runtime versions are preserved in `environment.txt`.
- Three within-bound/above-bound pairs (0.500/1.200, 0.650/1.100, 0.800/1.300 NTU), each with two A/B mappings. Within a pair, only the sensor value changes. All prompts and token IDs are saved.
- Each prompt is 143 tokens. Thinking mode is disabled for this one-token classification task. No simulator control APIs are called.
- Capture the last 12 token positions at all 36 decoder-layer outputs. Preserve the vectors in `activations.npz`; display relative RMS changes in the heatmap.
- Replace the full last-position decoder output vector at zero-based layers 6, 18, 30 and 35, in both directions: 48 interventions in total.
- Independently capture the within-bound prompt at layer 18 using NNsight, and compare its vector and output logits to the direct PyTorch pass. Self-patch that same prompt/layer as a no-op control. These controls cover that specific site in each case, not every layer and intervention.

All six pairs chose the expected next-token label for both readings. Patches at layers 6 and 18 changed the review-minus-hold logit gap by at most 0.109375 in magnitude. Patches at layer 30 reversed the binary preference in all six pairs, in both directions. Layer 35 reproduced the donor's logit gap, as expected when replacing the entire final decoder output at the readout position. The no-op and NNsight comparisons had zero maximum absolute error in this run (tolerance 0.02).

This demonstrates sensitivity and intervention effects on this constructed task. It does not localize a named circuit, recover a complete internal reasoning narrative, reproduce the 8B controller, or establish generalization. Whole-vector patches may create unusual internal states; the final-layer result is a broad positive control. Small earlier-layer effects can be comparable to float16 numerical resolution. More samples, matched controls, finer component interventions and a full control-task replay would be needed for stronger causal claims.

The displayed `P(review | A/B)` is a softmax restricted to those two candidate tokens. It is not calibrated confidence or physical risk. Full-vocabulary A/B mass is included to reveal if other next tokens are preferred. Emitted reasoning from the historical agent remains an output to audit against behavior, not a guaranteed faithful description of all internal computation.

## Reproduce locally

From the `water-ot-ai-lab` directory:

```bash
python3.13 -m venv .venv-interpret
.venv-interpret/bin/pip install -r requirements-interpretability.txt
.venv-interpret/bin/python scripts/run_mechanistic_probe.py
python3 scripts/research_evidence.py
cd services/web
npm ci
npm run dev -- --host 127.0.0.1 --port 18773
```

The probe expects the named cached Hugging Face revision under `~/.cache/huggingface/hub`; it runs offline and fails explicitly if the weights are unavailable. It defaults to MPS; `--device cpu` is available explicitly. Runs write new timestamped directories and retain partial/error evidence if a probe fails. A new export followed by **Reload evidence** adds the run to the dashboard.

Each run saves `results.json`, compressed activation arrays, PNG/SVG figures and checksums. The exporter records SHA-256 hashes of source JSON files. Downloads remain local; the static export contains raw prompt/response records, so inspect it before any later sharing. The current tool does not publish it.

## Verify

```bash
python3 -m unittest tests.test_research_evidence
.venv-interpret/bin/python -m unittest tests.test_research_evidence tests.test_mechanistic_probe
cd services/web
npm run build
```

The optional mechanistic tests skip when PyTorch is absent, so the ordinary simulator test environment does not require model libraries. The completed real run also has recorded NNsight/no-op controls. Browser checks cover study selection, decision jumping, threshold changes, prompt selection, activation navigation, downloads and desktop/mobile layout.

## Library references

- [NNsight](https://nnsight.net/) supports observing and intervening on local PyTorch models.
- [Transformers model outputs](https://huggingface.co/docs/transformers/main_classes/output) document hidden-state and logit access.
- [PyTorch module hooks](https://docs.pytorch.org/docs/stable/generated/torch.nn.Module.html) provide the decoder capture and intervention mechanism.
- [Qwen3 documentation](https://huggingface.co/docs/transformers/model_doc/qwen3) describes the model and thinking-mode template behavior.

## Typography and interface copy

The interface uses locally served IBM Plex Sans and IBM Plex Mono, with short subject labels. The seven-role rem scale, caption/body distinction and source references are in `services/web/DESIGN.md`. Methodological detail remains in notes and disclosures. The Impeccable typography assessment and detector ran independently; the final type scan reported no findings. Fonts retain their upstream license in `services/web/public/fonts`.
