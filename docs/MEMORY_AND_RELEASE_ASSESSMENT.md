# Context memory and open-source readiness

**Historical assessment, before the release implementation.** The reviewed-event memory, MIT license and release scaffolding have since been added. See [current memory behavior](REVIEWED_MEMORY.md) and [hosted deployment](HOSTED_SIMULATOR.md). The findings below document the earlier baseline.

Code and read-only runtime review, 17 September 2026. This document records implemented behaviour and proposed next steps. It does not claim a newly implemented learning loop or a completed release audit.

## Implemented memory

| Mechanism | What it does | Important boundary |
| --- | --- | --- |
| Persistent historian | Stores runs, samples, alarms, proposals, gate decisions and inference audits. Docker uses PostgreSQL on a named volume; the standalone default is SQLite. | Resetting a water run explicitly deletes that run's samples, decisions and alarms. This is not immutable retention. |
| Water scheduled-control retrieval | Examines the latest 100 decision records, selects the same scenario, ranks by numeric sensor similarity plus a recency penalty, then inserts selected episodes into the prompt. | Defaults to four episodes; configurable up to eight. It does not rank by incident severity or demonstrated improvement. A critical old episode can fall outside the candidate pool. |
| Water timeline context | With `include_history`, supplies the latest 12 samples and up to four prior exchanges from the same run/controller generation. Includes quality exceptions, alarms, proposals, gate dispositions and applied changes. | Opt-in, water only. The normal local worker-reviewer runner does not request this option. |
| Nuclear/grid context | Supplies recent trend values and the current state's prior audited decision. | This is not the water historical similarity-retrieval mechanism. |
| Local reviewer reports | Saves original evidence, reviewer requests, findings, citation checks and readable reports to local files. | Reports are not automatically promoted into future worker prompts or a learned policy. |

The runtime check returned `active_run_id: null` and memory `enabled: false`, with zero episodes. This means no active managed water run was supplying retrieved memory at inspection time; it does not mean the retrieval code is absent or disabled in every future configuration.

Source locations:

- `services/supervisor/app/database.py`: durable record tables.
- `services/supervisor/app/run_manager.py`: `_memory_context`, `reset`, `_ai_decision`, `memory_status`.
- `shared/models.py`: `RunConfig.memory_enabled` and `memory_window`.
- `services/supervisor/app/agents.py`: `water_history`, `cycle`, outcome observation.
- `services/supervisor/app/ollama_client.py`: structured context and instructions that memory is not authority.
- `scripts/local_agents.py`: saved reviews and independent fresh reviewer requests.

## What self-improvement would require

The current prototype provides contextual feedback and an audit trail. This review did not find a reward-driven policy update, model fine-tuning loop, automatic lesson promotion, or evidence that repeated use improves performance.

A proposed next increment is a versioned event-and-lesson memory:

1. Capture a critical event: excursion, rejected proposal, stale observation, ineffective adjustment, human override or recovery.
2. Join the event to its exact context, model/configuration version, action, gate decision and subsequent measured outcome. Distinguish temporal association from demonstrated causality.
3. Have a reviewer propose a lesson with source references and a confidence/uncertainty statement. The reviewer cannot approve its own conclusion as a new control rule.
4. Validate the lesson against deterministic checks, repeated simulation and human review where needed. Compare with memory disabled and ordinary retrieval.
5. Store approved, versioned lessons separately from raw incidents. Retrieve applicable lessons with expiry and contradiction handling; retain failures as well as successes.

Proposed evaluation: matched scenarios and seeds, fixed models, no-memory versus current memory versus reviewed lessons. Measure repeated mistakes, constraint violations, recovery, latency and resource use. Keep the control gate and safety limits outside the learning mechanism. Do not label a successful explanation as a successful physical outcome.

## Open-source release

The existing Docker setup, README, tests, simulated scenarios and local-model configuration are a useful starting point for a public research toolkit. This directory currently has no Git repository and no project-level open-source licence. Font licence files exist, but do not license the application itself. No public release was made in this review.

A concrete first release should package only the lab: application source, deployment configuration, simulated scenarios, tests, documented model setup and a curated recorded demo. Keep fellowship documents, local databases, environments, credentials, arbitrary audit dumps and private endpoint configuration outside the release. Review the exact release tree rather than assuming that `.gitignore` guarantees clean content; its current rules do not exclude every database or artifact.

Before publication:

- Confirm ownership and select a project licence; inventory dependency, font, model and example-data obligations. Model downloads should remain separate from the application release.
- Create a clean release tree and scan it for credentials, personal paths and unintended data. This review has not performed a full secret or licence scan.
- Verify the documented installation on a fresh environment, run the relevant tests, and provide a model-free recorded demo as well as the live Ollama path.
- Add contributor instructions, an issue template and a security-reporting route. Document tested hardware, simulation limits, retained evidence and how to clear it.
- Publish a versioned research release with reproducible example runs. Treat nuclear and grid models as simplified simulators, and keep operational deployment claims separate from research results.

General release guidance: [GitHub Open Source Guides — Starting a project](https://opensource.guide/starting-a-project/). The project-specific findings above come from the local code and files, not that guide.
