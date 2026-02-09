# Strategy implementation matrix

Purpose: track which parts of the strategy are implemented in code, where, and how to verify them.

## Legend

* ✅ done
* 🟨 partially done (scaffold exists, wiring missing)
* ⛔ not started

## Rails / determinism

| Area | Status | Where | How to verify |
|---|---:|---|---|
| Trade contract `trade_v1` | ✅ | `integration/trade_schema.json` + `integration/validate_trade_jsonl_json.py` | `python3 -m integration.validate_trade_jsonl_json --schema integration/trade_schema.json --jsonl integration/fixtures/trades.sample.jsonl` |
| Deterministic smoke | ✅ | `scripts/paper_runner_smoke.sh` + `integration/fixtures/expected_counts.json` | `bash scripts/paper_runner_smoke.sh` |
| stdout contract (`--summary-json`) | ✅ | `integration/paper_pipeline.py` | `python3 -m integration.paper_pipeline --dry-run --summary-json --trades-jsonl integration/fixtures/trades.sample.jsonl | wc -l` (must be 1) |

## Observability

| Area | Status | Where | How to verify |
|---|---:|---|---|
| run_trace_id propagation | ✅ | `integration/paper_pipeline.py` | check `summary.run_trace_id` in summary-json |
| Queryable rejects (`trade_reject`) | ✅ | `integration/write_trade_reject.py` + `strategy/docs/overlay/CLICKHOUSE_TRACE_VALIDATION.md` | run the ClickHouse queries from the doc |

## miniML interface

| Area | Status | Where | How to verify |
|---|---:|---|---|
| Feature contract v1 | ✅ | `features/trade_features.py` + `integration/fixtures/features_expected.json` | `bash scripts/features_smoke.sh` |
| Dataset export v1 | ✅ | `tools/export_training_dataset.py` | `python3 tools/export_training_dataset.py --trades-jsonl integration/fixtures/trades.sample.jsonl --out-csv /tmp/ds.csv` |
| Model interface (model_off) | ✅ | `integration/model_inference.py` | `python3 -c 'from integration.model_inference import infer_p_model; print(infer_p_model({}, mode="model_off"))'` |

## Next: Sprint-1 / Sprint-2

See `strategy/docs/overlay/SPRINT_PLAN.md`.