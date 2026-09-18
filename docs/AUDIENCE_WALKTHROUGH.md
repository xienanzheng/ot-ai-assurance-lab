# Ten-minute audience walkthrough

Open http://localhost:18780 on **Guided walkthrough**. Use **Presentation view**
for larger copy. Presenter notes are optional and visible on the shared screen;
leave them hidden if your audience should not see your script. The default tour
uses water. A technical audience can repeat it for nuclear or grid.

## Before the session

Run `docker compose up -d` and confirm **Local model ready**. Native Ollama starts
with the user session on this Mac. Keep a previously completed decision and paired
study in the inspector as real recorded evidence if live inference is slow.
The walkthrough's decisions and studies never actuate controls. Choose a healthy
baseline for an optimization proposal, or a disturbed state to demonstrate gate
rejection. Do not promise either result before observing it.

## 1. Meet the system — one minute

Say: “We are studying whether a local agent can help make supervisory decisions
while staying within an independently enforced boundary.”

Use the domain cards and process diagram. Show that each domain has its own
clock and operating state. The models are illustrative and isolated. Explain the
controller boundary before showing AI: sensors → deterministic loops → bounded
proposal → required gate. In the actual architecture, the gate authorizes targets
used by the existing controller; AI does not replace its protection loops.

## 2. Establish a baseline — two minutes

Click **Save previous exercise & prepare baseline**. This downloads the preceding
exercise before resetting the selected domain, runs five simulated minutes in
baseline mode, and pauses. Explain requested versus measured equipment feedback.
Use **Open clocks, alarms & event log** if an audience member asks for details;
return with the top Guided walkthrough tab. Captured observations survive tab
changes, but not a browser reload.

Say: “The process already works without AI. We need a reference condition before
we can compare any intervention.” Five minutes demonstrates the workflow, not
proof of steady state or a sufficiently long experimental baseline.

## 3. Introduce a disturbance — two minutes

Click **Run disturbance & capture response**. The app injects a predefined external
incident, steps ten simulated minutes, and pauses. Its 45-minute forcing remains
active until it expires or an operator ends it in the equipment desk.

Watch service coverage, sensors and alarm count. The grid event gives a clear
service shortfall; nuclear shows protective shutdown and station availability.
Water's storage and standby generation may preserve service initially: that is
resilience, not a failed demonstration. Discuss quality and storage as well as
immediate service coverage. Equivalent accounts are fictional service-deficit
estimates, not injuries, actual disconnected homes or city damage predictions.

## 4. Inspect the decision — three minutes

Click **Evaluate local agent · no actuation**. Leave reasoning capture off for a
shorter live call; enable it when you can allow one or two minutes. Explain the
boundary while the model works. If necessary, select **Load latest saved decision**
and explicitly tell the audience that it is a prior recorded run.

Show the proposed targets, rationale, gate status and specific rejection reasons.
Open the full inspector for exact inputs, generation settings, model digest and
emitted reasoning. A confident-looking explanation is not authority. A rejection
may be the correct outcome for a critical state. Accepted shadow evaluations still
apply nothing. Separate “gate permits this” from “this improves the process.”

## 5. Examine evidence — two minutes

Compare captured baseline and disturbance values. Export observations. State that
this comparison measures disturbance response; it does not establish an AI benefit.
Run the paired label study, or inspect a prior one with its timestamp. The process
inputs remain identical and only a socioeconomic label changes. The result is a
small exploratory observation with two inferences and zero actuation.

Finish with the actual next research question: under repeated matched conditions,
does gated local AI improve a predeclared objective without increasing constraint
violations, and does irrelevant context change its behavior? Study label ordering,
sensor uncertainty, memory, model version and generation settings. Reasoning text
is emitted evidence, not direct access to private internal computation.

## Technical discussion after the tour

Use the detailed control rooms for equipment, the Exercise console for trends and
alarm acknowledgements, Experiments for water-run configurations, and Local AI
agents for persisted decisions. To demonstrate actuation separately, use a paused,
healthy state in gated-auto mode and the inspector's live-gate option. Accepted
targets are leased, bounds remain enforced, and stale/reset/mode-changed proposals
are rejected. Do not mix that demonstration with the non-actuating tour results.
