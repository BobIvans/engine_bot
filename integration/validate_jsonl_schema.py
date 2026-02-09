#!/usr/bin/env python3
"""Generic JSONL validator for the repo's tiny schema format.

This mirrors `integration/validate_trade_jsonl_json.py`, but works for any
schema file under `integration/schemas/*_schema.json`.

It is intentionally dependency-free (no jsonschema).

Exit codes:
  0 OK
  2 Bad input (schema violation or invalid jsonl)
  3 Internal error
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional


EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_INTERNAL = 3


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _as_number(x: Any) -> Optional[float]:
    try:
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None


def load_schema(schema_path: str) -> Dict[str, Any]:
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    if not isinstance(schema, dict):
        raise ValueError("schema root must be an object")
    sv = schema.get("schema_version")
    if not isinstance(sv, str) or not sv:
        raise ValueError("schema_version must be a non-empty string")
    if not isinstance(schema.get("fields"), dict):
        raise ValueError("schema must contain object: fields")
    return schema


def validate_record(obj: Dict[str, Any], schema: Dict[str, Any], lineno: int) -> List[str]:
    errs: List[str] = []

    required = schema.get("required")
    if not isinstance(required, list):
        required = []

    for k in required:
        if k not in obj or obj[k] in (None, ""):
            errs.append(f"line {lineno}: missing_field:{k}")

    # schema_version (optional but strict if present)
    want_sv = schema.get("schema_version")
    if "schema_version" in obj and obj.get("schema_version") != want_sv:
        errs.append(f"line {lineno}: bad_schema_version:{obj.get('schema_version')!r}")

    fields = schema.get("fields", {})
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            continue
        is_optional = bool(spec.get("optional", False))
        if name not in obj:
            continue
        val = obj[name]

        if val in (None, ""):
            if not is_optional and name in required:
                errs.append(f"line {lineno}: empty_field:{name}")
            continue

        want_type = spec.get("type")
        want_types = spec.get("types")

        if want_types:
            ok = False
            if "string" in want_types and isinstance(val, str):
                ok = True
            if "number" in want_types and _as_number(val) is not None:
                ok = True
            if "integer" in want_types and isinstance(val, int) and not isinstance(val, bool):
                ok = True
            if not ok:
                errs.append(f"line {lineno}: bad_type:{name}={type(val).__name__}")
                continue

        elif want_type == "string":
            if not isinstance(val, str):
                errs.append(f"line {lineno}: bad_type:{name}={type(val).__name__}")
                continue
            ml = spec.get("min_length")
            if isinstance(ml, int) and len(val) < ml:
                errs.append(f"line {lineno}: too_short:{name}")
                continue

        elif want_type == "integer":
            if not isinstance(val, int) or isinstance(val, bool):
                errs.append(f"line {lineno}: bad_type:{name}={type(val).__name__}")
                continue

        elif want_type == "number":
            num = _as_number(val)
            if num is None:
                errs.append(f"line {lineno}: bad_type:{name}={type(val).__name__}")
                continue

        # enum/allowed
        allowed = spec.get("allowed")
        if isinstance(allowed, list) and val not in allowed:
            errs.append(f"line {lineno}: bad_value:{name}={val!r}")
            continue

        # constraints
        constraints = spec.get("constraints")
        if isinstance(constraints, dict):
            if "gt" in constraints:
                num = _as_number(val)
                if num is None or not (num > float(constraints["gt"])):
                    errs.append(f"line {lineno}: constraint_gt:{name}>{constraints['gt']}")
            if "ge" in constraints:
                num = _as_number(val)
                if num is None or not (num >= float(constraints["ge"])):
                    errs.append(f"line {lineno}: constraint_ge:{name}>={constraints['ge']}")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--max-errors", type=int, default=50)
    ap.add_argument("--format", choices=["text", "json"], default="text")
    args = ap.parse_args()

    try:
        schema = load_schema(args.schema)
    except Exception as e:
        _eprint(f"BAD_INPUT: failed to load schema: {e}")
        return EXIT_BAD_INPUT

    total = 0
    parsed = 0
    all_errs: List[str] = []

    try:
        with open(args.jsonl, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                total += 1
                try:
                    obj = json.loads(line)
                except Exception as e:
                    all_errs.append(f"line {lineno}: invalid_json:{type(e).__name__}")
                    if len(all_errs) >= args.max_errors:
                        break
                    continue
                if not isinstance(obj, dict):
                    all_errs.append(f"line {lineno}: invalid_json:not_object")
                    if len(all_errs) >= args.max_errors:
                        break
                    continue
                parsed += 1
                all_errs.extend(validate_record(obj, schema, lineno))
                if len(all_errs) >= args.max_errors:
                    break
    except FileNotFoundError:
        _eprint(f"BAD_INPUT: jsonl file not found: {args.jsonl}")
        return EXIT_BAD_INPUT
    except Exception as e:
        _eprint(f"INTERNAL: unexpected error: {type(e).__name__}: {e}")
        return EXIT_INTERNAL

    ok = len(all_errs) == 0

    if args.format == "json":
        print(
            json.dumps(
                {
                    "ok": ok,
                    "schema_version": schema.get("schema_version"),
                    "total_lines": total,
                    "parsed_lines": parsed,
                    "errors": all_errs[: args.max_errors],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if ok:
            print(
                f"[validate_jsonl_schema] OK schema={schema.get('schema_version')} total_lines={total} parsed_lines={parsed}"
            )
        else:
            for e in all_errs[: args.max_errors]:
                _eprint(e)
            _eprint(
                f"[validate_jsonl_schema] FAIL schema={schema.get('schema_version')} errors={len(all_errs)} total_lines={total}"
            )
    return EXIT_OK if ok else EXIT_BAD_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
