# SOP-informed timed supervision

User intent: improve Qwen and Jev decisions with plant procedures and observed, delayed responses; automatically feed the selected model new context; improve the gate; evaluate post-training. User authorizes planning and execution and leaves method selection to the implementer.

## Architecture

1. Versioned, simulator-specific SOPs contain applicability, required measurements, prerequisites, bounded target families, observation windows and escalation criteria. They are contextual guidance, never permission to bypass independent gates. Both providers receive the same selected procedures, recent applied actions and response observations.
2. A deterministic temporal gate supplements existing numerical/process gates: reject adjustments during observation windows, stale/bad-quality dependencies, repeated reversal and changes inconsistent with current response bounds. Hold/review remain possible. No SOP text changes numerical limits.
3. Opt-in feedback sessions use the simulation clock. The backend owns one serialized decision writer, a pinned provider, a maximum number of paid calls, an observation interval and explicit stop reasons. Pause suspends time-based decisions. Reset, mode change, emergency/protection, exhausted budget, timeout, invalid output or operator stop terminates the loop. Stop and in-flight cancellation prevent late application. Switching provider stops the old loop before starting another.
4. Response windows come from the simulator's actual first-order coefficients and valve slew limit, not invented physical-plant constants. Estimate effective lag and response trends from sampled observations, marking confounding and insufficient data. Lease length is server-selected up to 30 simulated minutes so a slow response can be observed before expiry. Single-shot decisions retain their five-minute default; loop leases match bounded observation windows. No automatic physical reset and no guarantee of recovery.
5. Local BERT-family cross-encoder reranking is optional, bounded and auditable; hosted falls back to deterministic SOP selection. Train/evaluate retrieval with held-out queries. Qwen gets a separate experimental SFT/LoRA pipeline and offline pilot using programmatic simulator training labels. No automatic model promotion; base and adapter evaluated on identical held-out cases. Jev uses SOP context, not a claimed private-weight fine-tune. RL/preference data is collected from trajectories, not immediate gate acceptance, and is not used to update a live policy.

## Acceptance

- Both providers' audits contain SOP version/hash, procedure IDs, observation timing and prior applied changes.
- No early re-adjustment, late action after stop/reset, overlapping model jobs or extra calls while paused.
- HMI remains driven by actual controls; UI displays waiting/running/stopped state, calls remaining and concise help.
- Tests cover model/provider failures, host quotas, stop during inference, reset, invalid sensors, slow response, lease expiry and withheld training splits.
- Record measured training/evaluation results and limitations; publish no credentials, private manual or model artifacts.
