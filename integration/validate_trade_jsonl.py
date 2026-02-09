#!/usr/bin/env python3
"""integration/validate_trade_jsonl.py

Validate a trades JSONL file against integration/trade_schema.yaml.

Exit codes:
  0 - OK
  2 - Bad input (schema mismatch, invalid JSON, missing fields, constraint fail)
  3 - Internal error

Notes:
  - This is a CI/smoke validator, not a replacement for trade_normalizer.
  - It is intentionally strict and deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

import yaml


EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_INTERNAL = 3


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _load_schema(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    if not isinstance(schema, dict):
        raise ValueError("schema root must be a mapping")
    return schema


def _as_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


def validate_record(obj: Dict[str, Any], schema: Dict[str, Any], lineno: int) -> List[str]:
    errs: List[str] = []

    required = schema.get("required") or []
    if not isinstance(required, list) or not all(isinstance(x, str) for x in required):
        required = ["ts", "wallet", "mint", "side", "price", "size_usd", "tx_hash"]

    # required fields present
    for k in required:
        if k not in obj or obj[k] in (None, ""):
            errs.append(f"line {lineno}: missing_field:{k}")

    # schema_version (optional, strict if present)
    if "schema_version" in obj and obj["schema_version"] != "trade_v1":
        errs.append(f"line {lineno}: bad_schema_version:{obj.get('schema_version')!r}")

    # side
    side = obj.get("side")
    if side not in ("BUY", "SELL", "buy", "sell"):
        errs.append(f"line {lineno}: bad_side:{side!r}")

    # price/size_usd positive
    price = _as_float(obj.get("price"))
    if price is None:
        errs.append(f"line {lineno}: bad_price:{obj.get('price')!r}")
    elif price <= 0:
        errs.append(f"line {lineno}: non_positive_value:price")

    size_usd = _as_float(obj.get("size_usd"))
    if size_usd is None:
        errs.append(f"line {lineno}: bad_size_usd:{obj.get('size_usd')!r}")
    elif size_usd <= 0:
        errs.append(f"line {lineno}: non_positive_value:size_usd")

    # platform (optional; if present, must be allowed)
    if "platform" in obj and obj.get("platform") not in (None, ""):
        p = str(obj.get("platform")).strip().lower()
        if p not in ("raydium", "jupiter", "pumpfun", "meteora", "other"):
            errs.append(f"line {lineno}: bad_platform:{p!r}")

    # ts minimal type check
    ts = obj.get("ts")
    if not isinstance(ts, (int, float, str)):
        errs.append(f"line {lineno}: bad_timestamp_type:{type(ts).__name__}")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True, help="Path to integration/trade_schema.yaml")
    ap.add_argument("--jsonl", required=True, help="Path to trades JSONL")
    ap.add_argument("--max-errors", type=int, default=50)
    args = ap.parse_args()

    try:
        schema = _load_schema(args.schema)
        errors: List[str] = []
        total_records = 0

        with open(args.jsonl, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    # strict: empty line is invalid JSON
                    errors.append(f"line {lineno}: invalid_json:empty_line")
                    if len(errors) >= args.max_errors:
                        break
                    continue

                total_records += 1
                try:
                    obj = json.loads(line)
                except Exception as e:
                    errors.append(f"line {lineno}: invalid_json:{type(e).__name__}")
                    if len(errors) >= args.max_errors:
                        break
                    continue

                if not isinstance(obj, dict):
                    errors.append(f"line {lineno}: invalid_json:not_object")
                    if len(errors) >= args.max_errors:
                        break
                    continue

                errors.extend(validate_record(obj, schema, lineno))
                if len(errors) >= args.max_errors:
                    break

        if errors:
            for e in errors[: args.max_errors]:
                _eprint(e)
            _eprint(f"[validate_trade_jsonl] FAIL errors={len(errors)} total_records={total_records}")
            return EXIT_BAD_INPUT

        _eprint(f"[validate_trade_jsonl] OK total_records={total_records}")
        return EXIT_OK

    except FileNotFoundError as e:
        _eprint(f"[validate_trade_jsonl] FAIL file_not_found: {e}")
        return EXIT_BAD_INPUT
    except Exception as e:
        _eprint(f"[validate_trade_jsonl] INTERNAL_ERROR {type(e).__name__}: {e}")
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
