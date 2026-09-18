# Local AI recovery timeline

Run `python3 scripts/run_recovery_timeline.py` with the Docker lab and native
Ollama running. The script creates a new water exercise, preserves the preceding
exercise/state, and runs the baseline comparison before the AI arm. It leaves the
last exercise paused. Each invocation creates a separate artifact directory.

## Protocol

- Same scenario, seed 42, reset state and one-minute PLC/plant stepping in both arms.
- Source turbidity ramps from 8 to 72 illustrative NTU during minutes 10–30,
  then stays at 72 plus seeded measurement/process noise. This constructed
  disturbance was selected with deterministic scenario checks to reach a warning
  band where existing gates can still admit corrective proposals. This is not a
  held-out benchmark. No forcing is removed to make recovery appear successful.
- Baseline uses existing automatic PLC control. The AI arm also starts on baseline;
  its first measured filter-effluent reading above 1.0 NTU enables `gated_auto`.
- The separate scheduled AI loop is disabled for these runs. One manual agent
  cycle occurs every four simulated minutes, renewing five-minute supervisory
  leases before expiry. No script chooses the model's numeric adjustments.
- Native `waterlab-water:latest` (Qwen3 8B) receives a requested 16K context, current
  sensors/quality, actual PLC targets and trips, illustrative limits and target
  change limits, the last 12 sensor samples and up to four prior live exchanges
  from the same run/controller generation. Full raw inputs and outputs are saved.
- The simulation clock pauses during inference. Wall-clock model latency is logged
  separately. This tests sequential decision-making; it does not establish that
  inference is fast enough for a continuously advancing process.
- The model reports `continue`, `resolved` or `escalate`. A resolved claim stops the
  run only after an independent check confirms eight contiguous simulated minutes
  inside the checked operating limits, good quality flags and no active alarms.
  An escalation stops the exercise for review; an unconfirmed claim does not.
- Runs stop at 60 minutes by default if unresolved. Failure, rejection and partial
  evidence are retained. An unsuccessful run is not relabelled as recovery.

The external disturbance remains active at the end. Pausing is the experiment's
termination action, not physical shutdown or removal of the disturbance. Gated
supervisory targets still have a finite lease; resuming past expiry can restore
previous targets and cause recurrence. A durable handover needs a separate study.

## Evidence and presentation

Each directory under `artifacts/recovery-timelines/` contains `report.html`,
`session.json`, both arms' CSV and exercise exports, and each complete agent record.
The HTML is a portable file with no external scripts: it plots the paired timeline,
shows every minute, and expands each exact prompt, emitted reasoning and gate.

Walk the audience through source deterioration, the baseline's response, the
threshold crossing, proposed versus applied controls and subsequent measurements.
Compare arms only through the same final simulated minute. The full 60-minute
baseline is also retained for inspection. A single constructed simulation cannot
establish general control performance, alignment or causal mechanisms inside an LLM.

The existing Agent Research Room also exposes each persisted local-agent record.
The portable report adds the experiment timeline and paired baseline comparison.
