# Advisory suggestions (Golden Ratio mini-ML) — P0-safe

This repo emits **advisory** suggestions for updating settings in `configs/golden_exit_engine.yaml`.
It never edits canonical config automatically.

## How it works
1) `tools/run_datagatherers.py` collects metrics into a snapshot folder (JSONL + manifest).
2) `tools/suggest_settings.py` reads a **rule-pack** YAML and evaluates rules on the gathered metrics.
3) The output is a patch-like YAML with suggested value(s) and rationale.

Golden Ratio (α≈0.618) is used as:
- a stable scaling factor for some rules, and
- a smoothing factor to avoid oscillations between iterations.

## Rule packs
Rule packs live in:
- `configs/suggestion_rulepacks/*.yaml` (non-canonical)

Validate:
```bash
python3 tools/validate_rulepack.py --rule-pack configs/suggestion_rulepacks/default.yaml
```

Suggest:
```bash
python3 tools/suggest_settings.py --snapshot-dir out/datagatherers/<...> --rule-pack configs/suggestion_rulepacks/default.yaml --out suggested_patch.yaml
```
