#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[dynamic_exec_smoke] Starting dynamic execution smoke test..." >&2
echo "[dynamic_exec_smoke] ROOT_DIR=${ROOT_DIR}" >&2

cd "${ROOT_DIR}"

unset PYTHONPATH
export PYTHONPATH="${ROOT_DIR}"

python3 - <<'PY'
import os, sys, inspect

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path = [p for p in sys.path if "strategy pack" not in (p or "")]

passed = 0
failed = 0

def ok(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"  [dynamic] {name}: PASS{(' ' + detail) if detail else ''}", file=sys.stderr)
        passed += 1
    else:
        print(f"  [dynamic] {name}: FAIL{(' ' + detail) if detail else ''}", file=sys.stderr)
        failed += 1

# Try to import dynamic module(s) without assuming exact structure.
# We support a couple common layouts.
dyn = None
for mod in ("strategy.dynamic_exec", "strategy.dynamic_execution", "integration.dynamic_exec", "integration.dynamic_execution"):
    try:
        dyn = __import__(mod, fromlist=["*"])
        mod_name = mod
        break
    except Exception:
        continue

if dyn is None:
    raise SystemExit("Could not import dynamic exec module (tried strategy/integration dynamic_exec*)")

print(f"[dynamic_exec_smoke] Using module: {mod_name} ({dyn.__file__})", file=sys.stderr)

# Find candidate functions.
# We look for ttl/slippage calculators and simulate_fill.
fn_ttl = getattr(dyn, "compute_dynamic_ttl_sec", None) or getattr(dyn, "dynamic_ttl_sec", None) or getattr(dyn, "compute_ttl_sec", None)
fn_slip = getattr(dyn, "compute_dynamic_slippage_bps", None) or getattr(dyn, "dynamic_slippage_bps", None) or getattr(dyn, "compute_slippage_bps", None)
fn_fill = getattr(dyn, "simulate_fill", None)

ok("has_ttl_fn", callable(fn_ttl))
ok("has_slippage_fn", callable(fn_slip))
ok("has_simulate_fill", callable(fn_fill))

if failed:
    raise SystemExit(1)

# Build minimal cfgs. Keep keys permissive: module should ignore unknown keys.
cfg_enabled = {
    "execution": {
        "dynamic": {
            "enabled": True,
            # Floors/clamps — even if module uses different keys, these won't hurt.
            "ttl_min_sec": 10,
            "ttl_max_sec": 600,
            "slippage_min_bps": 10,
            "slippage_max_bps": 500,
        }
    }
}
cfg_disabled = {"execution": {"dynamic": {"enabled": False}}}

# Minimal inputs: some modules want "trade" or "snapshot". We'll pass simple dicts.
trade_low = {"price": 1.0, "size_usd": 100.0, "vol_30s": 0.01}
trade_high = {"price": 1.0, "size_usd": 100.0, "vol_30s": 1.50}
snap_low = {"vol_30s": 0.01, "liquidity_usd": 50000.0}
snap_high = {"vol_30s": 1.50, "liquidity_usd": 50000.0}

def call(fn, *args):
    # Try a few common calling conventions
    for kwargs in (
        {"trade": args[0], "snapshot": args[1], "cfg": args[2]},
        {"trade": args[0], "snap": args[1], "cfg": args[2]},
        {"trade": args[0], "token_snapshot": args[1], "cfg": args[2]},
        {"snapshot": args[1], "cfg": args[2]},
        {"cfg": args[2]},
    ):
        try:
            return fn(**kwargs)
        except TypeError:
            continue
    # last resort: positional
    return fn(*args)

# --- TTL invariants ---
ttl_low = call(fn_ttl, trade_low, snap_low, cfg_enabled)
ttl_high = call(fn_ttl, trade_high, snap_high, cfg_enabled)
ok("ttl_returns_number", isinstance(ttl_low, (int, float)) and isinstance(ttl_high, (int, float)), f"(low={ttl_low}, high={ttl_high})")

# Expectation (robust): higher vol should NOT increase TTL (usually shorter TTL under higher vol).
# If your logic is opposite, this check can be flipped, but given current smoke naming, it likely expects low_vol >= high_vol.
ok("ttl_monotone_low_ge_high", ttl_low >= ttl_high, f"(low={ttl_low}, high={ttl_high})")

# TTL should be positive
ok("ttl_positive", ttl_low > 0 and ttl_high > 0)

# Disabled => should fallback to static/default TTL (we only check it's a number and not exploding)
ttl_dis = call(fn_ttl, trade_low, snap_low, cfg_disabled)
ok("ttl_disabled_number", isinstance(ttl_dis, (int, float)), f"(disabled={ttl_dis})")
ok("ttl_disabled_positive", ttl_dis > 0, f"(disabled={ttl_dis})")

# --- Slippage invariants ---
slip_low = call(fn_slip, trade_low, snap_low, cfg_enabled)
slip_high = call(fn_slip, trade_high, snap_high, cfg_enabled)
ok("slip_returns_number", isinstance(slip_low, (int, float)) and isinstance(slip_high, (int, float)), f"(low={slip_low}, high={slip_high})")

# Slippage should be non-negative
ok("slip_non_negative", slip_low >= 0 and slip_high >= 0, f"(low={slip_low}, high={slip_high})")

# Higher vol should not reduce slippage (usually higher vol => higher slippage)
ok("slip_monotone_low_le_high", slip_low <= slip_high, f"(low={slip_low}, high={slip_high})")

slip_dis = call(fn_slip, trade_low, snap_low, cfg_disabled)
ok("slip_disabled_number", isinstance(slip_dis, (int, float)), f"(disabled={slip_dis})")
ok("slip_disabled_non_negative", slip_dis >= 0, f"(disabled={slip_dis})")

# --- simulate_fill sanity (if present) ---
try:
    fill = call(fn_fill, trade_high, snap_high, cfg_enabled)
    ok("simulate_fill_returns", fill is not None)
except Exception as e:
    ok("simulate_fill_no_throw", False, f"({type(e).__name__}: {e})")

print(f"\n[dynamic_exec_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)
if failed:
    raise SystemExit(1)

print("[dynamic_exec_smoke] OK ✅", file=sys.stderr)
PY
