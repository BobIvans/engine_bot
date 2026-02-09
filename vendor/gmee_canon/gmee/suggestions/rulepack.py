from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

import yaml

@dataclass(frozen=True)
class RuleInput:
    gatherer: str
    field: str
    reduce: str = "max"

@dataclass(frozen=True)
class RuleTarget:
    key_path: str
    type: str = "float"  # "int" | "float" | "str"
    bounds_from: Optional[str] = None  # dot-path to {min,max} in engine config
    bounds: Optional[Dict[str, Any]] = None  # {min,max}

@dataclass(frozen=True)
class RuleTransform:
    kind: str  # "golden_linear" | "golden_affine"
    factor: float = 1.0
    base: float = 0.0
    smooth_with_current: bool = True

@dataclass(frozen=True)
class Rule:
    id: str
    enabled: bool
    description: str
    input: RuleInput
    target: RuleTarget
    transform: RuleTransform

@dataclass(frozen=True)
class RulePack:
    version: int
    defaults: Dict[str, Any]
    rules: List[Rule]

    @staticmethod
    def load(path: str) -> "RulePack":
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        version = int(cfg.get("version", 1))
        defaults = cfg.get("defaults", {}) or {}
        rules_cfg = cfg.get("rules", []) or []
        rules: List[Rule] = []
        for r in rules_cfg:
            ri = r.get("input", {}) or {}
            rt = r.get("target", {}) or {}
            rf = r.get("transform", {}) or {}
            rules.append(Rule(
                id=str(r.get("id")),
                enabled=bool(r.get("enabled", True)),
                description=str(r.get("description", "")),
                input=RuleInput(
                    gatherer=str(ri.get("gatherer")),
                    field=str(ri.get("field")),
                    reduce=str(ri.get("reduce", "max")),
                ),
                target=RuleTarget(
                    key_path=str(rt.get("key_path")),
                    type=str(rt.get("type", "float")),
                    bounds_from=rt.get("bounds_from"),
                    bounds=rt.get("bounds"),
                ),
                transform=RuleTransform(
                    kind=str(rf.get("kind", "golden_linear")),
                    factor=float(rf.get("factor", 1.0)),
                    base=float(rf.get("base", 0.0)),
                    smooth_with_current=bool(rf.get("smooth_with_current", True)),
                ),
            ))
        return RulePack(version=version, defaults=defaults, rules=rules)
