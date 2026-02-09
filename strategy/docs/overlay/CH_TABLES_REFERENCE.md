# ClickHouse tables reference (overlay)

This is a **short, human-maintained reference** used by agents and reviewers so
ClickHouse queries in this repo stay aligned with the real schema.

## Minimal contract assumed by overlay queries

The overlay validation queries assume there is an events-style table with at least:

- **ts**: event timestamp (DateTime/DateTime64)
- **run_trace_id**: deterministic trace id for a run (String)
- **kind**: event kind string, e.g. `trade_reject` (String)
- **details_json**: JSON string payload for the event details (String)

Common names used in environments:

- table: `forensics_events` (preferred in this repo)

If your environment uses different names/columns, **adapt the SQL snippets** in
`CLICKHOUSE_TRACE_VALIDATION.md` accordingly.

## Required event kinds

- `trade_reject` — emitted when a trade is rejected by normalizer/gates/risk.
