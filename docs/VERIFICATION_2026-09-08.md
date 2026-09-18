# Local equipment, agents and frontend verification

The offline container suite passed 99 tests; 3 opt-in network integration tests
were skipped. Added coverage includes auxiliary-command atomicity and permissives,
incident expiry and paused injection, standby availability, leased target restoration,
mode/reset/stale-context rejection, raw-output audit persistence, actual detached
gate evaluation and paired-study input isolation with zero actuation.

All application services are built and running locally. Native Ollama qwen3:8b
was exercised across water, nuclear and grid. Eight decision/study records survived
a supervisor restart. A grid proposal was accepted and applied through its gate,
a later sample was recorded, and its target returned to the previous value after
five simulated minutes. The first water output exceeded the four-target limit and
was rejected; the prompt was corrected to state that limit explicitly, and a later
water proposal with four targets was accepted in a non-actuating evaluation.

A real local grid reasoning call returned 3,584 characters of model-emitted reasoning.
The paired socioeconomic-label study returned two valid responses with identical
proposed controls and zero actuation. This is one exploratory pair, not proof of
alignment or absence of bias. Raw records and exercise exports are under
`artifacts/local-ai-verification/`.

Live predefined incidents produced reduced grid service and a nuclear protective
shutdown. The water walkthrough demonstrated baseline and storm observations,
with service initially preserved by the simplified storage/standby model. The final
paused-injection path removes a background-clock race from guided comparisons.

The production frontend built successfully. Browser checks covered the guided
landing page, domain navigation, water baseline/disturbance/inference flow, recorded
comparison, and desktop/mobile layouts. A 390px viewport had no document overflow;
no browser errors or framework overlays were observed. Screenshots are in artifacts.

These checks establish implementation behavior in an illustrative lab. They do not
calibrate the physics, establish real utility safety, or demonstrate a statistically
measured AI optimization benefit.
