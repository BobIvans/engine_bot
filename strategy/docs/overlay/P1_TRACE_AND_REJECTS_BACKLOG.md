# P1 (2 PR) — run_trace_id everywhere + trade_reject events (queryable by trace)

Below is a **two-PR checklist** for the next iteration. It is written so a coding agent can execute it **without interpretation**.

## Context / invariants

- Entrypoints are executed **only** via `python3 -m integration.*`.
- `integration.paper_pipeline --summary-json`:
  - **stdout = exactly one JSON line**
  - all human logs go to **stderr**
- Smoke already compares `counts` to `integration/fixtures/expected_counts.json` (do not break).
- CANON is read-only.

---

# PR#1 — P1.0 “run_trace_id through all entities (signals_raw / wallet_score / forensics)”

## Goal

One run can be reconstructed by filtering everything by `run_trace_id`:
- config/version forensics
- signals_raw
- wallet_score

## Checklist

1. Add a trace helper:
   - **Add** `integration/run_trace.py`
   - Functions:
     - `new_run_trace_id(prefix: str = "paper") -> str` returns `"paper-<uuid4>"`
     - `get_run_trace_id(cli_value: str | None) -> str` returns CLI value if provided else generates

2. Generate `run_trace_id` once in pipeline:
   - **Edit** `integration/paper_pipeline.py`
   - Add CLI arg: `--run-trace-id` (optional)
   - At start of `main()`: `run_trace_id = get_run_trace_id(args.run_trace_id)`
   - Ensure `--summary-json` always includes `run_trace_id`

3. Propagate `run_trace_id` into signals:
   - **Edit** `integration/write_signal.py`
   - Add/accept `run_trace_id` and include it inside `payload_json`
   - If the writer has a CLI: add `--run-trace-id` and pass through

4. Propagate `run_trace_id` into wallet_score:
   - **Edit** `integration/write_wallet_score.py`
   - Add/accept `run_trace_id` and include it inside `details_json`
   - If the writer has a CLI: add `--run-trace-id`

5. Forensics start/end events:
   - **Edit** `integration/paper_pipeline.py`
   - Emit:
     - `kind="run_start"` payload minimally `{run_trace_id, input_kind, input_path, config_hash, started_at}`
     - existing `kind="config_version"` / `kind="allowlist_version"` payloads MUST also include `run_trace_id`
     - `kind="run_end"` payload minimally `{run_trace_id, counts, finished_at}`

6. Smoke must remain unchanged:
   - `scripts/paper_runner_smoke.sh` stays green without updating `expected_counts.json`.

## DoD (PR#1)

- `bash scripts/paper_runner_smoke.sh` ✅ green
- `python3 -m integration.paper_pipeline --dry-run --summary-json ...` includes `run_trace_id`
- When CH is available, both `signals_raw` and `wallet_score` rows contain `run_trace_id` inside their JSON fields

---

# PR#2 — P1.1/P1.2 “trade_reject events in CH (queryable), stage=normalizer|gates, reason enum-only”

## Goal

All rejects (normalizer + gates) become queryable by `run_trace_id`.

## Checklist

1. Add a reject writer:
   - **Add** `integration/write_trade_reject.py`
   - Entrypoint: `python3 -m integration.write_trade_reject ...`
   - Writes to forensics as `forensics_events(kind="trade_reject")`
   - Payload JSON (minimum):
     - `run_trace_id` (str)
     - `stage` (str) in `{ "normalizer", "gates" }`
     - `reason` (str) from enum only
     - `lineno` (int)
     - optional if available: `tx_hash`, `wallet`, `mint`, `side`
     - optional: `detail` (short string)

2. Enforce enum-only reject reasons:
   - **Edit** `integration/reject_reasons.py`
   - Ensure it contains:
     - full list of reasons used by pipeline
     - `assert_reason_known(reason: str) -> None`
   - In `write_trade_reject.py`, call `assert_reason_known(reason)` (unknown reason -> INTERNAL)

3. Emit trade_reject from pipeline:
   - **Edit** `integration/paper_pipeline.py`
   - On normalizer reject:
     - emit `trade_reject` with `stage="normalizer"`, `reason=...`, `lineno=...` (+ fields if present)
   - On gates reject:
     - emit `trade_reject` with `stage="gates"`, `reason=...`, `lineno=...` (+ tx_hash/wallet/mint if present)
   - In `--dry-run`:
     - DO NOT write to CH
     - counts stay identical
     - do not pollute stdout (summary-json contract must hold)

4. Optional CH-only smoke:
   - **Edit** `scripts/p1_smoke.sh` or add `scripts/ch_rejects_smoke.sh`
   - Only run if CH env is present
   - Run edgecases without dry-run -> expect trade_reject rows
   - Minimal queries:
     - count trade_reject by `run_trace_id`
     - group by `stage, reason`

## DoD (PR#2)

- `bash scripts/paper_runner_smoke.sh` ✅ green (no CH required)
- With CH available: after edgecases run, `forensics_events(kind="trade_reject")` exists and can be filtered by `run_trace_id`

