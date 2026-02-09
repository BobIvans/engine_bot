# PR-4A.3 — Mode registry + metrics-by-mode (Variant A)

This PR makes strategy tuning measurable without rewriting core logic.

## Goals

- Add deterministic **mode registry** resolution (supports existing YAML layouts).
- Emit per-mode counters in `integration.paper_pipeline` summary JSON.
- Preserve **stdout contract**: when `--summary-json` is used, stdout must be **exactly 1 JSON line**.
- Keep rails green:
  - `bash scripts/overlay_lint.sh`
  - `bash scripts/paper_runner_smoke.sh`
  - `bash scripts/features_smoke.sh`
  - `bash scripts/config_smoke.sh`
  - `bash scripts/config_negative_smoke.sh`

## Hard rules

- DO NOT change `integration/fixtures/expected_counts.json`.
- DO NOT change `integration/trade_schema.json`.
- Any new logs go to **stderr only**.
- Any new smoke scripts must not print to stdout on success.

---

## Files (exact)

1) **NEW** `integration/mode_registry.py`
2) **MOD** `integration/paper_pipeline.py`
3) **MOD (optional, recommended)** `integration/validate_strategy_config.py` (validate resolved mode profiles, but do not require modes in base config)
4) **NEW** `integration/fixtures/config/modes_two_profiles.yaml`
5) **NEW** `integration/fixtures/trades.modes_two_profiles.jsonl`
6) **NEW** `integration/fixtures/expected_modes_two_profiles.json`
7) **NEW** `scripts/modes_smoke.sh`
8) **MOD** `scripts/overlay_lint.sh` (call `bash scripts/modes_smoke.sh` before final OK)

---

## Part A — Mode registry (single source of truth)

**NEW file:** `integration/mode_registry.py`

Implement:

```python
def resolve_modes(cfg: dict) -> dict[str, dict]:
    ...
```

Resolution priority:

1) Root `modes` as mapping: `modes: {U: {...}, S: {...}}`
2) Root `modes` as list: `modes: [{name: U, ...}, {name: S, ...}]`
3) Fallback path: `cfg["signals"]["modes"]["base_profiles"]` (mapping or list)

Normalization rules:

- Return a dict keyed by mode name: `{"<MODE>": { ...mode_cfg... }, ...}`
- For list forms: each entry must be mapping and have a non-empty string `name`.
- If invalid entries exist, **skip them** (do not raise in `resolve_modes`).
- If no modes found anywhere: return `{}`.

**Grep-point:**

- `grep -n "def resolve_modes" integration/mode_registry.py`

---

## Part B — paper_pipeline: per-mode counters in summary-json

**MOD file:** `integration/paper_pipeline.py`

When producing the summary JSON (the single line printed to stdout under `--summary-json`), add:

```python
summary["mode_counts"] = {
  "<MODE>": {
    "total_lines": int,
    "normalized_ok": int,
    "rejected_by_normalizer": int,
    "rejected_by_gates": int,
    "filtered_out": int,
    "passed": int,
  },
  ...
}
```

Determinism rules:

- All counters are integers; default 0.
- For each input line, exactly one bucket is chosen.

Mode assignment rules per trade line:

1) If trade has `mode` (string) and it matches a resolved mode name → use it.
2) Else if `U` exists in resolved modes → use `U`.
3) Else if resolved modes not empty → use first mode in `sorted(resolved_modes.keys())`.
4) Else → use `__no_mode__`.

If trade has an explicit `mode` string that is **not** in resolved modes:

- bucket under `__unknown_mode__` (do not error).

Where to increment counters:

- `total_lines`: every non-empty non-comment JSONL input line (even if rejected by normalizer).
- `normalized_ok` / `rejected_by_normalizer`: same decision point as global counts.
- `rejected_by_gates` / `filtered_out` / `passed`: increment in the same places as existing global counters.

Backward compatibility:

- Existing global counts remain unchanged.
- Adding `mode_counts` must not affect `paper_runner_smoke.sh` (no expected-count changes).

**Grep-point:**

- `grep -n "mode_counts" integration/paper_pipeline.py`

---

## Part C — Optional validator enhancement (non-breaking)

**MOD file (optional):** `integration/validate_strategy_config.py`

- Use `resolve_modes(cfg)`.
- If it returns non-empty dict, validate each mode profile with existing guardrails:
  - `ttl_sec`: int > 0
  - `tp_pct`: number > 0
  - `sl_pct`: number < 0
  - `hold_sec_min`: int >= 0
  - `hold_sec_max`: int >= hold_sec_min
  - `max_slippage_bps`: if present, int >= 0

Error format (stderr only, stable & greppable):

- `ERROR: Invalid mode profile <MODE>: ttl_sec expected int > 0, got=<VAL>`
- `ERROR: Invalid mode profile <MODE>: tp_pct expected number > 0, got=<VAL>`
- `ERROR: Invalid mode profile <MODE>: sl_pct expected number < 0, got=<VAL>`
- `ERROR: Invalid mode profile <MODE>: hold_sec_min expected int >= 0, got=<VAL>`
- `ERROR: Invalid mode profile <MODE>: hold_sec_max expected int >= hold_sec_min, got min=<MIN> max=<MAX>`
- `ERROR: Invalid mode profile <MODE>: max_slippage_bps expected int >= 0, got=<VAL>`

Exit codes unchanged:

- `0` ok
- `2` validation errors
- `1` runtime errors

Non-goal: do not require modes for base configs that currently omit them.

---

## Part D — Fixtures for modes smoke

### D1) `integration/fixtures/config/modes_two_profiles.yaml`

Define two valid modes: `X` and `Y` using root-level mapping form:

```yaml
modes:
  X:
    ttl_sec: 60
    tp_pct: 1.0
    sl_pct: -1.0
    hold_sec_min: 0
    hold_sec_max: 10
    max_slippage_bps: 50
  Y:
    ttl_sec: 60
    tp_pct: 1.0
    sl_pct: -1.0
    hold_sec_min: 0
    hold_sec_max: 10
    max_slippage_bps: 50
```

If the paper pipeline config loader needs additional keys, mirror them minimally from `strategy/config/params_base.yaml`.

### D2) `integration/fixtures/trades.modes_two_profiles.jsonl`

- Exactly 2 lines.
- Both lines must be valid inputs for the normalizer (trade_v1 or accepted raw records).
- Reuse wallet/mint patterns from `integration/fixtures/trades.sample.jsonl` for stability.
- Line 1 must include: `"mode":"X"`
- Line 2 must include: `"mode":"Y"`

**Grep-points:**

- `grep -n '"mode":"X"' integration/fixtures/trades.modes_two_profiles.jsonl`
- `grep -n '"mode":"Y"' integration/fixtures/trades.modes_two_profiles.jsonl`

### D3) `integration/fixtures/expected_modes_two_profiles.json`

Keep it minimal and non-fragile:

```json
{
  "schema_version": "modes_counts.v1",
  "expected_mode_names": ["X", "Y"],
  "expected_total_lines": 2,
  "expected_mode_totals": {"X": 1, "Y": 1}
}
```

---

## Part E — New smoke: `scripts/modes_smoke.sh`

Requirements:

- bash, `set -euo pipefail`
- Must NOT print anything to stdout on success.
- Must print failures to stderr only, each starting with `ERROR: modes_smoke:`

Command (matches current `integration.paper_pipeline` CLI):

```bash
python3 -m integration.paper_pipeline --dry-run --summary-json \
  --config integration/fixtures/config/modes_two_profiles.yaml \
  --allowlist strategy/wallet_allowlist.yaml \
  --token-snapshot integration/fixtures/token_snapshot.sample.csv \
  --wallet-profiles integration/fixtures/wallet_profiles.sample.csv \
  --trades-jsonl integration/fixtures/trades.modes_two_profiles.jsonl
```

Assertions:

1) stdout has EXACTLY 1 non-empty line
   - `ERROR: modes_smoke: expected stdout=1 line, got <N>`
2) JSON parses
   - `ERROR: modes_smoke: invalid JSON on stdout`
3) required keys exist: `counts` and `mode_counts`
   - `ERROR: modes_smoke: summary missing key: <key>`
4) `mode_counts` has buckets `X` and `Y`, each has `total_lines == 1`
   - `ERROR: modes_smoke: mode_counts missing mode: <MODE>`
   - `ERROR: modes_smoke: mode <MODE> total_lines expected=1 got=<VAL>`
5) sum(mode_counts[*].total_lines) == counts.total_lines == 2
   - `ERROR: modes_smoke: total_lines mismatch: counts.total_lines=<A> sum(mode_counts.total_lines)=<B>`

On success, print to stderr exactly one line:

- `[modes_smoke] OK ✅`

**Grep-point:**

- `grep -n "ERROR: modes_smoke:" scripts/modes_smoke.sh`

---

## Part F — Wire into overlay_lint

**MOD file:** `scripts/overlay_lint.sh`

Add (near other lint calls, before final OK):

```bash
bash scripts/modes_smoke.sh
```

---

## DoD

All must pass:

1) `bash scripts/config_smoke.sh`
2) `bash scripts/config_negative_smoke.sh`
3) `bash scripts/modes_smoke.sh`
4) `bash scripts/overlay_lint.sh`
5) `bash scripts/paper_runner_smoke.sh`
6) `bash scripts/features_smoke.sh`

Expected:

- paper pipeline summary JSON remains exactly 1 line.
- `mode_counts` appears and is internally consistent.
- Existing rails remain unchanged.
