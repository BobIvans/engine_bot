# RUNTIME_CONFIG_LAYOUT

## Схема директорий

- Docs-only (агент читает, рантайм игнорирует):
  - `strategy/docs/**`
  - `strategy/docs/overlay/**`

- Runtime конфиг (код читает):
  - `strategy/config/params_base.yaml`
  - `strategy/config/modes.yaml` (опционально)
  - `strategy/wallet_allowlist.yaml`
  - `strategy/wallet_features_example.json`

- CANON (read-only):
  - `vendor/gmee_canon/**`

## Как код читает конфиг
- `integration/config_loader.py`:
  - грузит YAML
  - валидирует “минимальный контракт”
  - считает `config_hash` (sha256 от bytes файла)
- Runner (paper/sim) пишет `forensics_events(kind="config_version")` при старте.
