# Premium trial capture → long-lived reproducible artifacts (P0-safe)

Goal: turn a 24–72h premium-access window into *forever useful* datasets **without** changing P0 canon
(SQL/YAML/DDL/docs). You capture what the license allows, hash it, normalize it into "universal variables", and
anchor everything to your own trace/trade labels.

## What you get (deliverables)
- **RAW snapshots**: `out/capture/raw/<provider>/<snapshot_id>/raw.jsonl` + `raw_meta.json`
- **Universal Variables (UV)**: `out/capture/uv/<provider>/<snapshot_id>/uv.jsonl` + `uv_meta.json`
- **Trade labels** (optional): `out/capture/labels/<snapshot_id>/trade_labels.jsonl`
- **Snapshot manifest**: `out/capture/snapshots/<snapshot_id>/snapshot_manifest.json`

Everything is pinned by SHA256 in the manifest.

## 0) Before the trial window starts
1) Create a mapping YAML for the provider export format:
- start from one of:
  - `configs/providers/mappings/example_wallet_labels.yaml`
  - `configs/providers/mappings/example_pool_metrics.yaml`
  - `configs/providers/mappings/example_route_execution.yaml`

2) Decide your stable snapshot ids (one per day/session):
- `trial_<provider>_day1`, `trial_<provider>_day2`, ...

3) Decide license tags:
- something you can audit later, e.g. `nansen_trial_2025Q1`

## 1) During the trial window: capture RAW (primary truth)
Export provider responses (API export, CSV dump, UI export) into JSONL.
Then:

```bash
python tools/capture_raw_snapshot.py \
  --provider example_pool_metrics \
  --license-tag PROVIDER_TRIAL_2025Q1 \
  --plan trial \
  --input provider_export.jsonl \
  --out-dir out/capture \
  --snapshot-id trial_example_pool_day1
```

## 2) Normalize into Universal Variables

```bash
python tools/normalize_to_universal_vars.py \
  --mapping configs/providers/mappings/example_pool_metrics.yaml \
  --raw out/capture/raw/example_pool_metrics/trial_example_pool_day1/raw.jsonl \
  --out-dir out/capture
```

## 3) Derive labels from your *own* trades (optional but recommended)

```bash
export CLICKHOUSE_HTTP_URL=http://localhost:8123
python tools/export_trade_labels.py \
  --since 2025-01-01T00:00:00.000Z \
  --until 2025-01-02T00:00:00.000Z \
  --snapshot-id trial_example_pool_day1 \
  --out-dir out/capture
```

Labels include `confirm_quality` and `exclude_from_training` logic (P0 contract).

## 4) Build the snapshot manifest (pins hashes)

```bash
python tools/build_dataset_snapshot.py \
  --snapshot-id trial_example_pool_day1 \
  --out-dir out/capture \
  --provider example_pool_metrics \
  --notes "Day1 premium trial export"
```

## 5) One-command alternative
If you already have provider export JSONL:

```bash
python tools/premium_trial_pipeline.py \
  --provider example_pool_metrics \
  --license-tag PROVIDER_TRIAL_2025Q1 \
  --plan trial \
  --input provider_export.jsonl \
  --mapping configs/providers/mappings/example_pool_metrics.yaml \
  --snapshot-id trial_example_pool_day1 \
  --since 2025-01-01T00:00:00.000Z --until 2025-01-02T00:00:00.000Z
```

## Notes on compliance
- Store only what your license/ToS permits.
- Keep `license_tag` and `plan` in RAW meta so datasets remain auditable.
- If you cannot store raw payloads, store hashed summaries and the normalized UV layer.
