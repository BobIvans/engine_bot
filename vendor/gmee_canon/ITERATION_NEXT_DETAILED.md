# ITERATION_NEXT_DETAILED (P0-safe)

This file is *non-canonical* and exists to plan next iterations **without touching**:
docs/*, configs/*, schemas/*, queries/*, scripts/*.

## Newly added in v8
- Evidence bundle export: `gmee/evidence.py` + `tools/export_evidence_bundle.py`
- Evidence bundle replay: `gmee/replay.py` + `tools/replay_evidence_bundle.py`
- Roundtrip test (integration): `tests/test_evidence_bundle_roundtrip.py`

## Next micro-iterations (optional, still P0)
1) Evidence bundle "trace scope"
   - Export all `trade_id`s under a `trace_id` into one bundle folder (subfolders per trade).
   - Add manifest index with per-trade sha256/row-count.

2) Evidence bundle "minimal oracle mode"
   - Export only tables used by glue_select (trades, microticks_1s, wallet_profile_30d view deps).
   - Use this for ultra-fast CI.

3) Replay hardening
   - Add `--force` to clear rows for trade_id before replay (TRUNCATE WHERE emulation via ALTER TABLE ... DELETE).
   - Keep default behavior skip-existing (safe).

4) Deterministic export sorting
   - Ensure all exports ORDER BY canonical keys (already done).
   - Add `--no-sort-keys` fast mode if needed (not default).

5) Forensics enrichment (schema unchanged)
   - Add `details_json` standard schema keys:
     - `contract_version`, `sdk_version`, `source_module`
     - `time_skew_ms` with all pairwise deltas
   - Emit only through `gmee/forensics.py`.
