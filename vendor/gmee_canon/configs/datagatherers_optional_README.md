# Optional DataGatherers (non-canonical)

`configs/datagatherers.yaml` is the default registry used by `tools/run_datagatherers.py`.

This optional file provides **additional generic gatherers** for new variables/sources beyond wallets:
- `window_delta`: detect metric drift between recent vs baseline windows.
- `cooccurrence`: joint distribution of categorical pairs.

Run with:
```bash
python3 tools/run_datagatherers.py --chain solana --env live --registry configs/datagatherers_optional.yaml
```
