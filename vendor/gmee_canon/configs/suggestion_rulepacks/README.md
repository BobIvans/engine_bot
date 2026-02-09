# Suggestion rule-packs (non-canonical)

These YAML files control **advisory** settings suggestions without changing code.

- They **do not** modify canonical configs automatically.
- They are safe to iterate in parallel with P0 (no schema/SQL changes).
- A rule evaluates gathered metrics (DataGatherer snapshot JSONL) and proposes a patch.

Run:
```bash
python3 tools/suggest_settings.py --snapshot-dir out/datagatherers/<...> --rule-pack configs/suggestion_rulepacks/default.yaml
```

Rule semantics (minimal):
- `input.gatherer`: key in snapshot manifest (e.g. `rpc_arm_stats`)
- `input.field`: field name in rows (numeric)
- `input.reduce`: `max|min|mean|p50|p90|p99`
- `target.key_path`: dot-path inside `configs/golden_exit_engine.yaml`
- `target.bounds_from`: dot-path to `{min,max}` object in engine config
- `transform.kind`:
  - `golden_linear`: `raw = alpha * factor * metric`
  - `golden_affine`: `raw = alpha * (base + factor * metric)`
  - then optional clamp and smoothing with current (golden-alpha)
