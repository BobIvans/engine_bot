from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math
import os

from .rulepack import RulePack, Rule

GOLDEN_RATIO = (1 + 5 ** 0.5) / 2
GOLDEN_ALPHA = 1 / GOLDEN_RATIO  # ~0.618 (golden-ratio conjugate)

@dataclass(frozen=True)
class Suggestion:
    key_path: str
    current_value: Any
    suggested_value: Any
    rationale: str
    rule_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


def _dot_get(cfg: Any, path: str) -> Any:
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(path)
        cur = cur[part]
    return cur


def _percentile(vals: List[float], q: float) -> float:
    if not vals:
        raise ValueError("empty")
    xs = sorted(vals)
    if len(xs) == 1:
        return float(xs[0])
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    frac = pos - lo
    return float(xs[lo] * (1 - frac) + xs[hi] * frac)


def _reduce_numeric(vals: List[float], how: str) -> float:
    how = (how or "max").lower()
    if not vals:
        raise ValueError("empty")
    if how == "max":
        return float(max(vals))
    if how == "min":
        return float(min(vals))
    if how == "mean":
        return float(sum(vals) / len(vals))
    if how in ("p50", "median"):
        return _percentile(vals, 0.50)
    if how == "p90":
        return _percentile(vals, 0.90)
    if how == "p99":
        return _percentile(vals, 0.99)
    raise ValueError(f"unknown reduce: {how}")


class SuggestionEngine:
    """Rule-pack driven advisory suggestions.

    P0-safe: does NOT mutate canonical config; emits suggestions only.
    """

    def __init__(self, engine_cfg: Dict[str, Any], rule_pack_path: Optional[str] = None):
        self.engine_cfg = engine_cfg
        self.rule_pack_path = rule_pack_path

    def load_rule_pack(self) -> Optional[RulePack]:
        if not self.rule_pack_path:
            return None
        if not os.path.exists(self.rule_pack_path):
            return None
        return RulePack.load(self.rule_pack_path)

    def run(self, gathered: Dict[str, List[Dict[str, Any]]]) -> List[Suggestion]:
        rp = self.load_rule_pack()
        if not rp:
            # Back-compat: if no rulepack is provided, do nothing (explicit is better).
            return []
        alpha = float(rp.defaults.get("alpha", GOLDEN_ALPHA))
        out: List[Suggestion] = []
        for rule in rp.rules:
            if not rule.enabled:
                continue
            sug = self._apply_rule(rule, gathered, alpha)
            if sug:
                out.append(sug)
        return out

    def _apply_rule(self, rule: Rule, gathered: Dict[str, List[Dict[str, Any]]], alpha: float) -> Optional[Suggestion]:
        rows = gathered.get(rule.input.gatherer) or []
        # collect numeric values
        vals: List[float] = []
        for r in rows:
            v = r.get(rule.input.field)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except Exception:
                continue
        if not vals:
            return None

        metric = _reduce_numeric(vals, rule.input.reduce)

        # current value
        try:
            cur_val = _dot_get(self.engine_cfg, rule.target.key_path)
        except KeyError:
            return None

        # bounds
        lo: Optional[float] = None
        hi: Optional[float] = None
        if rule.target.bounds_from:
            try:
                b = _dot_get(self.engine_cfg, str(rule.target.bounds_from))
                lo = float(b.get("min"))
                hi = float(b.get("max"))
            except Exception:
                lo = hi = None
        if rule.target.bounds:
            lo = float(rule.target.bounds.get("min", lo if lo is not None else -math.inf))
            hi = float(rule.target.bounds.get("max", hi if hi is not None else math.inf))

        # raw transform
        k = rule.transform.kind
        if k == "golden_linear":
            raw = alpha * (rule.transform.factor * metric)
        elif k == "golden_affine":
            raw = alpha * (rule.transform.base + rule.transform.factor * metric)
        else:
            return None

        # clamp
        clamped = raw
        if lo is not None:
            clamped = max(lo, clamped)
        if hi is not None:
            clamped = min(hi, clamped)

        # smooth with current
        cur_f = float(cur_val) if isinstance(cur_val, (int, float)) else None
        final = clamped
        if rule.transform.smooth_with_current and cur_f is not None:
            final = alpha * clamped + (1 - alpha) * cur_f

        # coerce type
        tgt_t = rule.target.type.lower()
        if tgt_t == "int":
            suggested = int(round(final))
            current = int(round(cur_f)) if cur_f is not None else cur_val
        elif tgt_t == "float":
            suggested = float(round(final, 6))
            current = float(cur_f) if cur_f is not None else float(cur_val)
        else:
            return None

        if suggested == current:
            return None

        parts = [f"rule={rule.id}", f"metric={rule.input.gatherer}.{rule.input.field}", f"reduce={rule.input.reduce}", f"metric_value={metric:.6g}", f"alpha≈{alpha:.3f}"]
        if lo is not None and hi is not None:
            parts.append(f"clamp=[{lo},{hi}]")
        rationale = "; ".join(parts)
        return Suggestion(
            key_path=rule.target.key_path,
            current_value=current,
            suggested_value=suggested,
            rationale=rationale,
            rule_id=rule.id,
        )
