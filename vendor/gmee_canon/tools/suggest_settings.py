#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from gmee.suggestions import SuggestionEngine

def load_snapshot_dir(p: Path) -> Dict[str, List[Dict[str, Any]]]:
    manifest = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
    gathered: Dict[str, List[Dict[str, Any]]] = {}
    for g in manifest.get("gatherers", []):
        name = g["name"]
        rows: List[Dict[str, Any]] = []
        with (p / g["file"]).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        gathered[name] = rows
    # Optional: fused snapshot features (created by tools/fuse_snapshot.py)
    fused = p / "fused_features.jsonl"
    if fused.exists():
        rows = []
        with fused.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        gathered["fused"] = rows
    return gathered

def load_metrics_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-dir", required=False, help="output directory created by tools/run_datagatherers.py")
    ap.add_argument("--metrics-jsonl", required=False, help="external JSONL metrics file (one dict per line)")
    ap.add_argument("--metrics-name", default="rpc_arm_stats", help="name to register external metrics under")
    ap.add_argument("--engine-yaml", default="configs/golden_exit_engine.yaml")
    ap.add_argument("--rule-pack", default="configs/suggestion_rulepacks/default.yaml", help="non-canonical rule pack YAML for suggestions")
    ap.add_argument("--out", default=None, help="write patch suggestions to this file (YAML)")
    args = ap.parse_args()

    engine_cfg = yaml.safe_load(Path(args.engine_yaml).read_text(encoding="utf-8"))

    if args.metrics_jsonl:
        gathered = {args.metrics_name: load_metrics_jsonl(Path(args.metrics_jsonl))}
    else:
        if not args.snapshot_dir:
            raise SystemExit("Need either --snapshot-dir or --metrics-jsonl")
        gathered = load_snapshot_dir(Path(args.snapshot_dir))

    eng = SuggestionEngine(engine_cfg, rule_pack_path=args.rule_pack)
    suggestions = eng.run(gathered)

    if not suggestions:
        print("No suggestions.")
        return 0

    for s in suggestions:
        print(f"- {s.key_path}: {s.current_value} -> {s.suggested_value}  ({s.rationale})")

    if args.out:
        patch = {"suggestions": [s.__dict__ for s in suggestions], "rule_pack": args.rule_pack}
        Path(args.out).write_text(yaml.safe_dump(patch, sort_keys=False), encoding="utf-8")
        print(f"Wrote: {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
