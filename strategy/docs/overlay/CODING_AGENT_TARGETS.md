# Coding agent targets (overlay)

This repo is designed for an agent to land strategy work safely. The rule is simple:

1) **Follow rails.** Never break the deterministic smokes.
2) **Follow the task registry** (no improvisation): `strategy/docs/overlay/SPRINTS.md`.
3) When a PR has a dedicated spec doc, follow it 1:1.

## Rails that must stay green

- `bash scripts/overlay_lint.sh`
- `bash scripts/paper_runner_smoke.sh` (stdout=exactly 1 JSON line guard)
- `bash scripts/features_smoke.sh`
- `bash scripts/config_smoke.sh`
- `bash scripts/config_negative_smoke.sh`

## Current next task

Variant A (tunable config + observability):

- **PR-4A.3: Mode registry + metrics-by-mode**
  - Spec: `strategy/docs/overlay/PR_MODES.md`
  - Goal: normalize config modes in one place and emit `mode_counts` in paper pipeline summary JSON while preserving the 1-line stdout contract.

## After PR-4A.3

- Variant A: tuning playbook (docs + templates)
- Sprint-2 track: risk engine v1 → sim → +EV (see `strategy/docs/overlay/SPRINTS.md`)
