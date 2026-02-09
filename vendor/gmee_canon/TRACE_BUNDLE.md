# Trace-scope evidence bundle (P0)

This repo supports **trace-scope bundles**: one directory that indexes all trades for a `trace_id`,
plus per-trade sub-bundles compatible with the existing replay/oracle gates.

## Export
```bash
python3 tools/export_evidence_bundle.py --trace-id <TRACE_UUID> --out /tmp/gmee_trace_bundle
```

Output:
- `trace_manifest.json`
- `trace_signals_raw.jsonl`
- `trace_forensics_events.jsonl` (optional)
- `trades/<trade_id>/...` (each is a normal trade evidence bundle)

## Replay
```bash
# safe mode (default): skip when rows exist
python3 tools/replay_evidence_bundle.py --bundle /tmp/gmee_trace_bundle

# force mode: delete existing rows for this trace/trades then insert (mutations_sync=2)
python3 tools/replay_evidence_bundle.py --bundle /tmp/gmee_trace_bundle --force
```

## External capture snapshots (optional)

If you used the premium capture pipeline (`out/capture/...`) and built one or more
`snapshot_manifest.json` files, investigations can automatically link the relevant
snapshots to a trade/trace **without copying RAW/UV data into the bundle**.

How it works:

- `gmee_doctor --investigate-trade-id ...` (and `tools/one_button_investigate.py`) will:
  - resolve `trace_id` from `trade_id`
  - export a trace-scope evidence bundle
  - **match snapshots** whose `observed_range` covers the trade `buy_time`
  - **attach** `external_capture_ref` rows into `forensics_events.details_json` (soft-fail if CH write fails)
  - render `report.html`

Bundle additions when snapshots match:

- `capture_refs.jsonl` — which snapshots/providers were linked (bundle-local index)
- `external_snapshot_paths.json` — references to the original capture file locations + sha256 pins
- `external_snapshots/<snapshot_id>/snapshot_manifest.json` — copied manifest(s) for offline review

This keeps bundles small while preserving reproducibility (manifest + sha256 + source paths).
