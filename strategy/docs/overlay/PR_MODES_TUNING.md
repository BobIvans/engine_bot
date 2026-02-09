# PR-4A.5: Modes tuning playbook

## What is a mode
A **mode** is a named tuning profile (e.g. `U/S/M/L`, or custom names like `X/Y`) used to:
- select configuration parameters, and
- bucket outcomes deterministically in metrics.

Deterministic data flow:
1) Trade JSONL may contain a string field `mode`.
2) The normalizer preserves it into `Trade.extra["mode"]`.
3) `paper_pipeline --summary-json` emits `mode_counts` so each run is auditable by mode.

## Guardrails
Always run these before trusting results:
- `bash scripts/config_smoke.sh`
- `bash scripts/config_negative_smoke.sh`
- `bash scripts/modes_smoke.sh`
- `bash scripts/paper_runner_smoke.sh`

Hard rules for tuning work:
- **Never change** `integration/fixtures/expected_counts.json` during tuning PRs.
- Any tuning change must be isolated to **config changes** (YAML) + an explicit results record.
- Keep stdout contracts intact (especially `paper_pipeline --summary-json`: stdout must be exactly 1 JSON line).

Mode bucketing rules (as implemented in PR-4A.3/4A.4):
- If trade has a known mode that exists in the resolved registry → bucket into that mode.
- If trade has a mode that is not in the registry → bucket into `__unknown_mode__`.
- If trade has no mode field → fallback to `U` if present, else the first key of sorted registry.
- If registry is empty → bucket into `__no_mode__`.

## Tuning loop
1) Copy config (never overwrite base without a commit):
   - create a new YAML under `strategy/config/` or `integration/fixtures/config/`.
2) Run a deterministic pipeline pass and capture summary JSON:
   - run with `--summary-json` and redirect stdout to a file.
3) Compare `mode_counts` deltas and key counters:
   - totals, passed, rejected_by_gates, filtered_out (overall and by mode).
4) Record results using the template below (commit the row with the PR).
5) Keep changes small: one hypothesis per PR.

## Results template
Copy-paste friendly table (append rows per experiment):

| date | config_path | modes | trace_id | fixture | total_lines | passed_total | passed_by_mode | rejected_by_gates_by_mode | notes |
|---|---|---|---|---:|---:|---:|---|---|---|
| 2026-01-11 | strategy/config/params_base.yaml | X,Y | <run_trace_id> | trades.sample.jsonl | 123 | 45 | X:20; Y:25 | X:5; Y:8 | baseline run |

Required columns:
- `date`, `config_path`, `modes`, `trace_id`, `fixture`, `total_lines`, `passed_total`, `passed_by_mode`, `rejected_by_gates_by_mode`, `notes`

## Example: two-mode experiment
Goal: compare two profiles `X` vs `Y` while keeping everything else fixed.

Checklist:
- Create `integration/fixtures/config/modes_two_profiles.yaml` with `modes: {X: {...}, Y: {...}}`.
- Add two trades with explicit modes (`"mode":"X"`, `"mode":"Y"`) to a small JSONL fixture.
- Run pipeline and verify summary has `mode_counts.X` and `mode_counts.Y` and totals match.
- Append one row to the Results template with the trace id and key counters.
