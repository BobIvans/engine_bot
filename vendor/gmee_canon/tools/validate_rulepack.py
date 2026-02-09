#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import yaml

from gmee.suggestions import RulePack

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule-pack", default="configs/suggestion_rulepacks/default.yaml")
    args = ap.parse_args()

    rp = RulePack.load(args.rule_pack)
    print(f"OK: version={rp.version} rules={len(rp.rules)}")
    for r in rp.rules:
        print(f"- {r.id} enabled={r.enabled} target={r.target.key_path} input={r.input.gatherer}.{r.input.field} reduce={r.input.reduce}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
