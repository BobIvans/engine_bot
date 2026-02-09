#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict

import yaml

from gmee.clickhouse import ClickHouseQueryRunner
from gmee.datagatherer import DataGathererRegistry, GatherContext
from gmee.util import repo_root

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--registry", default="configs/datagatherers.yaml", help="non-canonical DataGatherer registry YAML")
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--out", default="out/datagatherers")
    ap.add_argument("--ch-url", default=os.environ.get("CLICKHOUSE_URL", "http://localhost:8123"))
    ap.add_argument("--db", default=os.environ.get("CLICKHOUSE_DATABASE"))
    args = ap.parse_args()

    root = repo_root()
    engine_cfg = yaml.safe_load((root / "configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))
    reg = DataGathererRegistry.load(str(root / args.registry))

    u = urlparse(args.ch_url)
    host = u.hostname or 'localhost'
    port = u.port or 8123
    ch = ClickHouseQueryRunner(host=host, port=port, database=(args.db or 'default'))
    ctx = GatherContext(ch=ch, engine_cfg=engine_cfg, env=args.env, chain=args.chain, database=args.db, since_ts=args.since, until_ts=args.until)

    gathered = reg.run_all(ctx)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) / f"{args.chain}_{args.env}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "chain": args.chain,
        "env": args.env,
        "since": args.since,
        "until": args.until,
        "generated_at": ts,
        "gatherers": [],
    }

    for name, rows in gathered.items():
        fn = out_dir / f"{name}.jsonl"
        with fn.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        manifest["gatherers"].append({
            "name": name,
            "rows": len(rows),
            "file": fn.name,
            "sha256": sha256_file(fn),
        })

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(out_dir))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
