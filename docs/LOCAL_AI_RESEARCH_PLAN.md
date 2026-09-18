# Local AI controls and alignment research plan

Requested sequence: complete equipment and resilience exercises, then verify local
AI agents, gate every action, and inspect their decisions in repeatable studies.

1. Expand all three equipment models and expose command, feedback, availability,
   runtime, plant sensor values and service consequences. Validate physical
   accounting and preserve independent protections.
2. Install native Ollama with the configured qwen3:8b model. Keep cloud features
   off. Deterministic PLC/protection loops remain primary; AI proposes bounded
   supervisory setpoints and cannot call equipment or incident endpoints.
3. Persist each inference request, returned rationale, optional model-emitted
   reasoning, structured proposal, validation failure, gate outcome and subsequent
   measurements. Display exact provenance and distinguish fallback from AI.
4. Add controlled, non-actuating studies: equivalent-input label permutations,
   repeated identical cases, conflicting optimization pressure, sensor-quality
   uncertainty and prohibited-action probes. Report observed inconsistencies,
   confidence, rejection rates and sample sizes; do not infer latent intent from
   generated prose or call a model aligned based on a small test suite.

Reasoning text is model-provided evidence, not privileged access to the model's
internal computation. Gate enforcement and measured behavior are separate
observable evidence. Simulated incidents use fictional external disturbances;
this lab does not predict offsite radiation, casualties or real city damage.

## Implementation status

Equipment and incident controls, native local inference, durable decision audits,
deterministic gates, bounded leases and three paired pilot studies are implemented.
The Guided walkthrough provides a five-chapter audience path with baseline and
disturbance capture, no-actuation inference and linked raw evidence. Sensor-quality
sweeps, randomized label ordering, larger evaluation sets, confidence intervals and
trained predictive optimizers remain further research work; the current model makes
bounded supervisory proposals from observed state. See LOCAL_AI_OPERATOR_GUIDE.md
and AUDIENCE_WALKTHROUGH.md for the implemented workflow.
