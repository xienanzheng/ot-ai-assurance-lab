# Sharing snapshot — November 10, 2026

Public repository: [xienanzheng/ot-ai-assurance-lab](https://github.com/xienanzheng/ot-ai-assurance-lab).

Use branch **`docs/friends-quickstart`** for the installation guides and packaged local workshop. It is based on public `main` at `944f80f`; the new workshop snapshots V2 source revision `9278a4c`. The separately measured experiment was executed at `20a709f`. `workshops/local-qwen/SOURCE.json` records the original source file hashes; the training guide lists packaging changes.

| Shared | Location |
|---|---|
| Main simulator source | Repository root |
| First-install guide and configuration helper | `docs/QUICKSTART.md`, `scripts/setup_local.py` |
| Explanation of training versus context changes | `docs/LOCAL_POSTTRAINING.md` |
| Standalone water/cooling V2 bench | `workshops/local-qwen/` |
| Local LoRA procedure, cases, SOPs and tests | Workshop `TRAINING.md`, `training/`, `process_packages/`, `tests/` |
| Historical base/adapter evaluation rows | Workshop `evidence/typed-qwen-2026-10-31/` |

Local uncommitted frontend/Cloudflare changes, the newer V1 scenario/teacher work, personal presentations, private manuals, visitor data and API credentials are not swept into this branch. The Jev pilot is described as historical work; its collector is not part of the executable workshop. This branch does not deploy either website, upload weights or replace the current model.

The 4B adapter remains unapproved. Friends download the upstream base themselves and can create their own offline research adapter. The packaged test cases are public teaching material; a new improvement claim needs newly frozen evaluation cases.
