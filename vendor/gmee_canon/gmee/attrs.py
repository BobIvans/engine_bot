from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, Iterable, Mapping, Tuple


def flatten_json(obj: Any, prefix: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Deterministically flatten a JSON-like object into key-path -> scalar.
    Lists are indexed (e.g. a.0.b). Dict keys are kept.
    """
    out: Dict[str, Any] = {}

    def rec(x: Any, p: str) -> None:
        if isinstance(x, dict):
            for k in sorted(x.keys(), key=lambda s: str(s)):
                rec(x[k], f"{p}{sep}{k}" if p else str(k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                rec(v, f"{p}{sep}{i}" if p else str(i))
        else:
            out[p] = x

    rec(obj, prefix)
    return out


def safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return None


def extract_attribute_counts(
    json_strings: Iterable[str],
    *,
    max_keys: int = 2000,
    max_value_len: int = 200,
) -> Tuple[Counter[str], Dict[str, Counter[str]]]:
    """
    Generic & replicable attribute harvesting for NEW data variables.

    Returns:
      - key_counts: how often each key-path appears
      - value_counts: for each key-path, top values (stringified, capped)
    """
    key_counts: Counter[str] = Counter()
    value_counts: Dict[str, Counter[str]] = {}

    for s in json_strings:
        obj = safe_json_loads(s)
        if obj is None:
            continue
        flat = flatten_json(obj)
        for k, v in flat.items():
            key_counts[k] += 1
            if len(value_counts) < max_keys and k not in value_counts:
                value_counts[k] = Counter()
            if k in value_counts:
                sv = "" if v is None else str(v)
                if len(sv) > max_value_len:
                    sv = sv[:max_value_len] + "…"
                value_counts[k][sv] += 1

    # trim value_counts to most common values per key
    for k in list(value_counts.keys()):
        value_counts[k] = Counter(dict(value_counts[k].most_common(20)))

    return key_counts, value_counts
