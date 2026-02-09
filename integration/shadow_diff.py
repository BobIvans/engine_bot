#!/usr/bin/env python3
"""
PR-E.1 Paper vs Live Shadow Diff CLI Tool

Compares paper simulation results with live execution.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List


def _load_jsonl(path: str) -> List[dict[str, Any]]:
    """Load JSONL file and return list of dicts."""
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def compute_diff(paper_trades: list[dict[str, Any]], live_trades: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute shadow diff between paper and live trades.
    
    Args:
        paper_trades: List of paper trade records
        live_trades: List of live trade records
        
    Returns:
        Diff metrics dictionary
    """
    # Index trades by signal_id (or trace_id as fallback)
    paper_by_id: dict[str, dict[str, Any]] = {}
    live_by_id: dict[str, dict[str, Any]] = {}
    
    for trade in paper_trades:
        trade_id = trade.get("signal_id") or trade.get("trace_id")
        if trade_id:
            paper_by_id[trade_id] = trade
    
    for trade in live_trades:
        trade_id = trade.get("signal_id") or trade.get("trace_id")
        if trade_id:
            live_by_id[trade_id] = trade
    
    # Inner join by signal_id/trace_id
    matched_ids = set(paper_by_id.keys()) & set(live_by_id.keys())
    
    rows: list[dict[str, Any]] = []
    total_entry_slippage_bps = 0.0
    fill_match_count = 0
    
    for trade_id in sorted(matched_ids):
        paper = paper_by_id[trade_id]
        live = live_by_id[trade_id]
        
        # Calculate entry slippage in bps
        paper_price = paper.get("fill_price") or paper.get("price") or 0
        live_price = live.get("fill_price") or live.get("price") or 0
        
        if paper_price and paper_price != 0:
            slippage_bps = ((live_price - paper_price) / paper_price) * 10000
        else:
            slippage_bps = 0.0
        
        total_entry_slippage_bps += slippage_bps
        
        # Check fill status match
        paper_filled = paper.get("filled", True)
        live_filled = live.get("filled", True)
        fill_match = paper_filled == live_filled
        if fill_match:
            fill_match_count += 1
        
        # Calculate PnL drift
        paper_pnl = paper.get("pnl_usd") or paper.get("pnl") or 0
        live_pnl = live.get("pnl_usd") or live.get("pnl") or 0
        pnl_drift = live_pnl - paper_pnl
        
        rows.append({
            "signal_id": trade_id,
            "paper_price": paper_price,
            "live_price": live_price,
            "slippage_bps": round(slippage_bps, 4),
            "paper_filled": paper_filled,
            "live_filled": live_filled,
            "fill_match": fill_match,
            "paper_pnl_usd": paper_pnl,
            "live_pnl_usd": live_pnl,
            "pnl_drift_usd": round(pnl_drift, 4),
        })
    
    # Calculate aggregate metrics
    num_matched = len(rows)
    
    if num_matched > 0:
        avg_entry_slippage_bps = total_entry_slippage_bps / num_matched
        fill_match_rate = fill_match_count / num_matched
    else:
        avg_entry_slippage_bps = 0.0
        fill_match_rate = 0.0
    
    # Calculate fill rates for divergence
    paper_filled_count = sum(1 for t in paper_trades if t.get("filled", True))
    live_filled_count = sum(1 for t in live_trades if t.get("filled", True))
    
    paper_fill_rate = paper_filled_count / len(paper_trades) if paper_trades else 0.0
    live_fill_rate = live_filled_count / len(live_trades) if live_trades else 0.0
    fill_rate_divergence = live_fill_rate - paper_fill_rate
    
    # Total PnL drift across all matched trades
    total_pnl_drift = sum(r["pnl_drift_usd"] for r in rows)
    
    return {
        "schema_version": "diff_metrics.v1",
        "title": "PR-E shadow diff",
        "run": {
            "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "summary": {
            "rows_matched": num_matched,
            "fill_match_rate": round(fill_match_rate, 4),
            "avg_entry_slippage_bps": round(avg_entry_slippage_bps, 4),
            "fill_rate_divergence": round(fill_rate_divergence, 4),
            "total_pnl_drift_usd": round(total_pnl_drift, 4),
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare paper simulation results with live execution"
    )
    parser.add_argument("--paper", required=True, help="Path to paper trades JSONL file")
    parser.add_argument("--live", required=True, help="Path to live trades JSONL file")
    parser.add_argument("--out", required=True, help="Output path for results JSON")
    
    args = parser.parse_args()
    
    try:
        # Load trades from JSONL files
        paper_trades = _load_jsonl(args.paper)
        live_trades = _load_jsonl(args.live)
        
        # Compute diff
        diff_metrics = compute_diff(paper_trades, live_trades)
        
        # Write output
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(diff_metrics, f, indent=2)
        
        # Success: stderr only
        sys.stderr.write("[shadow_diff] OK ✅\n")
        
    except Exception as e:
        sys.stderr.write(f"[shadow_diff] ERROR: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
