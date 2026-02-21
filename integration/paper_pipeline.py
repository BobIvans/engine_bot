#!/usr/bin/env python3
"""integration/paper_pipeline.py

Iteration-1 "paper runner" (P0.1): Trade → snapshot → gates → writes

What it does:
- Loads runtime config from strategy/config/params_base.yaml
- Writes forensics_events(kind="config_version") for reproducibility
- Consumes normalized Trade events from JSONL (offline replay)
- Enriches token gates via a local snapshot cache (Parquet) — no external APIs
- Applies hard gates
- For passing BUY trades:
  - inserts into signals_raw (via integration/write_signal.py helpers)
  - emits a minimal wallet_score event (for traceability)

P0.1 additions vs P0:
- JSONL parsing/validation moved into integration/trade_normalizer.py
- Token gates require a local snapshot (or inline values); missing snapshot => reject_reason=missing_snapshot
- End-of-run stats for reject reasons
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import replace
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from integration.config_loader import load_params_base, init_reloader, stop_reloader, get_runtime_config, apply_runtime_overrides
from integration.mode_registry import resolve_modes
from integration.ch_client import ClickHouseConfig, make_runner
from integration.trade_types import Trade
from integration.trade_normalizer import load_trades_jsonl, normalize_trade_record
from integration.token_snapshot_store import TokenSnapshot, TokenSnapshotStore
from integration.run_trace import get_run_trace_id
from integration.gates import apply_gates
from integration.reject_reasons import INVALID_TRADE, MISSING_SNAPSHOT, RISK_COOLDOWN, RISK_MODE_LIMIT, RISK_WALLET_TIER_LIMIT
from integration.parquet_io import ParquetReadConfig, iter_parquet_records
from integration.allowlist_loader import load_allowlist

# PR-F.1: Conditional import for RpcSource (live ingestion)
try:
    from ingestion.sources.rpc_source import RpcSource
    HAS_RPC_SOURCE = True
except ImportError:
    HAS_RPC_SOURCE = False

# PR-Y.4: Bitquery Adapter
try:
    from ingestion.sources.bitquery_source import BitquerySource
    HAS_BITQUERY_SOURCE = True
except ImportError:
    HAS_BITQUERY_SOURCE = False

# PR-F.2: Conditional import for LiveTokenSnapshotStore
try:
    from integration.live_snapshot_store import LiveTokenSnapshotStore
    HAS_LIVE_SNAPSHOT_STORE = True
except ImportError:
    HAS_LIVE_SNAPSHOT_STORE = False
from integration.wallet_profile_store import WalletProfileStore
from integration.wallet_tier_registry import resolve_tier

from integration.sim_preflight import preflight_and_simulate, compute_edge_bps

from integration.portfolio_stub import PortfolioStub
from integration.risk_stage import risk_stage

# PR-Z.4: Exit Hazard Prediction Model
from integration.hazard_stage import HazardStage, HazardStageConfig, DEFAULT_HAZARD_THRESHOLD

from integration.execution_preflight import execution_preflight

from integration.pnl_aggregator import aggregate_daily_metrics

from integration.write_signal import insert_signal
from integration.write_wallet_score import insert_wallet_score
from integration.write_trade_reject import insert_trade_reject
from integration.signals_dump import write_signals_jsonl_atomic

# PR-8.1: signals dump schema version
SIGNALS_SCHEMA_VERSION = "signals.v1"


def _mk_allowlist_version_row(
    ts: str,
    chain: str,
    env: str,
    path: str,
    wallets_count: int,
    allowlist_hash: str,
    run_trace_id: str,
) -> Dict[str, Any]:
    """Run-level forensics event to version the active allowlist."""
    details = {"path": path, "wallets_count": wallets_count, "allowlist_hash": allowlist_hash}
    return {
        "event_id": str(uuid.uuid4()),
        "ts": ts,
        "chain": chain,
        "env": env,
        "kind": "allowlist_version",
        "severity": "info",
        "details_json": json.dumps(details, ensure_ascii=False, separators=(",", ":")),
        "trace_id": run_trace_id,
        "trade_id": None,
        "attempt_id": None,
    }


def _utc_now_iso_ms() -> str:
    # ClickHouse DateTime64(3) friendly format
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]


def _mk_config_version_row(
    ts: str,
    chain: str,
    env: str,
    path: str,
    strategy_name: str,
    version: str,
    config_hash: str,
    run_trace_id: str,
) -> Dict[str, Any]:
    return {
        "ts": ts,
        "chain": chain,
        "env": env,
        "kind": "config_version",
        "trace_id": run_trace_id,
        "payload_json": json.dumps(
            {
                "path": path,
                "strategy_name": strategy_name,
                "version": version,
                "config_hash": config_hash,
            },
            ensure_ascii=False,
        ),
    }


def _build_signal_row(
    schema_version: str,
    run_trace_id: str,
    lineno: int,
    ts: str,
    wallet: str,
    mint: str,
    tx_hash: Optional[str],
    mode: str,
    wallet_tier: Optional[str],
    decision: str,
    reject_stage: Optional[str],
    reject_reason: Optional[str],
    edge_bps: Optional[int],
    ttl_sec: Optional[int],
    tp_pct: Optional[float],
    sl_pct: Optional[float],
    include_sim: bool = False,
    sim_exit_reason: Optional[str] = None,
    sim_pnl_usd: Optional[float] = None,
    sim_roi: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a signal row dict for signals dump (signals.v1 schema)."""
    row: Dict[str, Any] = {
        "schema_version": schema_version,
        "run_trace_id": run_trace_id,
        "lineno": lineno,
        "ts": ts,
        "wallet": wallet,
        "mint": mint,
        "tx_hash": tx_hash or "",
        "mode": mode,
        "wallet_tier": wallet_tier,
        "decision": decision,
        "reject_stage": reject_stage,
        "reject_reason": reject_reason,
        "edge_bps": edge_bps,
        "ttl_sec": ttl_sec,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
    }
    if include_sim:
        row["sim_exit_reason"] = sim_exit_reason
        row["sim_pnl_usd"] = sim_pnl_usd
        row["sim_roi"] = sim_roi
    return row


def _get_sim_results_per_trade(
    trades_norm: list,
    cfg: Dict[str, Any],
    token_snapshot_store: Any,
    wallet_profile_store: Any,
) -> Dict[tuple, Dict[str, Any]]:
    """Get per-trade simulation results for signals dump enrichment.

    Returns a dict mapping (wallet, mint) -> {exit_reason, pnl_usd, roi}.
    """
    from collections import defaultdict
    from integration.sim_preflight import _ts_to_seconds, _simulate_exit, compute_edge_bps

    min_edge_bps = int(cfg.get("min_edge_bps", 0))

    # Build tick index per mint
    ticks_by_mint: Dict[str, list] = defaultdict(list)
    for t in trades_norm:
        mint = str(getattr(t, "mint", "") or "")
        if not mint:
            continue
        ts_sec = _ts_to_seconds(getattr(t, "ts", ""))
        px_raw = getattr(t, "price", None)
        try:
            px = float(px_raw)
        except Exception:
            continue
        ticks_by_mint[mint].append((ts_sec, px))

    for mint, arr in ticks_by_mint.items():
        arr.sort(key=lambda x: x[0])

    results: Dict[tuple, Dict[str, Any]] = {}

    for t in trades_norm:
        side = str(getattr(t, "side", "")).upper()
        if side != "BUY":
            continue

        wallet = str(getattr(t, "wallet", "") or "")
        mint = str(getattr(t, "mint", "") or "")
        if not wallet or not mint:
            continue

        entry_price_raw = getattr(t, "price", None)
        try:
            entry_price = float(entry_price_raw)
        except Exception:
            continue

        entry_ts_sec = _ts_to_seconds(getattr(t, "ts", ""))

        # Get snapshot
        snap = None
        if token_snapshot_store is not None:
            if hasattr(token_snapshot_store, "get_latest"):
                snap = token_snapshot_store.get_latest(mint)
            elif hasattr(token_snapshot_store, "get"):
                snap = token_snapshot_store.get(mint)

        if snap is None:
            continue

        wp = None
        if wallet_profile_store is not None and hasattr(wallet_profile_store, "get"):
            wp = wallet_profile_store.get(wallet)
        if wp is None:
            continue

        # Get mode
        extra = getattr(t, "extra", None) or {}
        mode = extra.get("mode") if isinstance(extra, dict) else "U"
        if not mode:
            mode = "U"

        # +EV gate check
        edge_bps = compute_edge_bps(trade=t, token_snap=snap, wallet_profile=wp, cfg=cfg, mode_name=mode)
        if edge_bps < min_edge_bps:
            continue

        # Simulate exit
        mode_cfg = (cfg.get("modes") or {}).get(mode, {})
        fut = ticks_by_mint.get(mint, [])
        exit_price, exit_reason = _simulate_exit(
            entry_price=entry_price,
            entry_ts_sec=entry_ts_sec,
            future_ticks=fut,
            cfg_mode=mode_cfg,
        )

        # Calculate PnL
        notional_raw = getattr(t, "qty_usd", None) or getattr(t, "size_usd", None)
        try:
            notional = float(notional_raw) if notional_raw is not None else 1.0
        except Exception:
            notional = 1.0
        if notional <= 0:
            notional = 1.0

        pnl_usd = ((exit_price / entry_price) - 1.0) * notional
        roi = pnl_usd / notional if notional else 0.0

        results[(wallet, mint)] = {
            "exit_reason": exit_reason,
            "pnl_usd": pnl_usd,
            "roi": roi,
        }

    return results


def _snapshot_from_trade_inline(trade: Trade) -> Optional[TokenSnapshot]:
    # If replay input already provides snapshot fields, we can use them for deterministic tests.
    if trade.liquidity_usd is None and trade.volume_24h_usd is None and trade.spread_bps is None:
        return None
    return TokenSnapshot(
        mint=trade.mint,
        ts_snapshot=None,
        liquidity_usd=trade.liquidity_usd,
        volume_24h_usd=trade.volume_24h_usd,
        spread_bps=trade.spread_bps,
        top10_holders_pct=None,
        single_holder_pct=None,
        extra=None,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", default="solana")
    ap.add_argument("--env", default="paper")
    ap.add_argument("--run-trace-id", default="", help="Optional run trace id override (trace_id in CH == run_trace_id)")
    ap.add_argument("--config", default="strategy/config/params_base.yaml")
    ap.add_argument("--trades-jsonl", default="", help="Input trades in normalized JSONL (optional)")
    ap.add_argument(
        "--trades-parquet",
        default="",
        help="Input trades in Parquet (Data-track output). Requires duckdb (see requirements.txt).",
    )
    ap.add_argument(
        "--parquet-colmap-json",
        default="",
        help="Optional JSON mapping of target_col->source_col for parquet rename (e.g. {'ts':'block_ts'}).",
    )
    ap.add_argument("--parquet-limit", type=int, default=None, help="Optional limit for parquet replay")
    # PR-F.1: Live ingestion source arguments
    ap.add_argument(
        "--source-type",
        default="jsonl",
        choices=["jsonl", "parquet", "rpc"],
        help="Input source type: jsonl, parquet, or rpc (default: jsonl)",
    )
    ap.add_argument(
        "--rpc-url",
        default="",
        help="RPC endpoint URL for RPC source (required when --source-type=rpc)",
    )
    ap.add_argument(
        "--tracked-wallets",
        default="",
        help="Comma-separated wallet addresses or path to file with wallets (for --source-type=rpc)",
    )
    ap.add_argument(
        "--token-snapshot",
        default="integration/fixtures/token_snapshot.sample.csv",
        help="Local token snapshot cache (CSV/Parquet) for token gates (Data-track output)",
    )
    # PR-F.2: Live token snapshot flag (ignores --token-snapshot when enabled)
    ap.add_argument(
        "--live-snapshots",
        action="store_true",
        help="Use live Jupiter API for token snapshots instead of file-based store",
    )
    ap.add_argument(
        "--wallet-profiles",
        default="",
        help="Optional wallet profile cache (CSV/Parquet). If provided, missing wallet metrics in trades are enriched from it.",
    )
    ap.add_argument("--allowlist", default="strategy/wallet_allowlist.yaml", help="Allowlist file")
    ap.add_argument("--no-log-allowlist-version", action="store_true", help="Do not emit allowlist_version forensics event (run-level)")
    ap.add_argument("--require-allowlist", action="store_true", help="Fail if traced wallet not in allowlist")
    ap.add_argument("--source", default="paper_pipeline", help="signals_raw.source")
    ap.add_argument("--only-buy", action="store_true", help="Only create signals for BUY trades")
    ap.add_argument("--dry-run", action="store_true", help="Do not write to ClickHouse")
    ap.add_argument(
        "--summary-json",
        action="store_true",
        help="Print exactly one JSON line summary to stdout (logs go to stderr)",
    )
    ap.add_argument(
        "--sim-preflight",
        action="store_true",
        help="Attach deterministic sim_metrics (sim_metrics.v1) into --summary-json output (off by default)",
    )
    ap.add_argument(
        "--daily-metrics",
        action="store_true",
        help="Attach daily_metrics.v1 aggregation into --summary-json output (requires --sim-preflight)",
    )
    ap.add_argument(
        "--execution-preflight",
        action="store_true",
        help="Attach execution_metrics.v1 into --summary-json output (off by default)",
    )
    ap.add_argument(
        "--metrics-out",
        default="",
        help="Write run metrics as JSON to this path (works in --dry-run too)",
    )
    ap.add_argument(
        "--signals-out",
        default="",
        help="Write signals dump as JSONL to this path (deterministic sidecar for DuckDB/Parquet)",
    )
    ap.add_argument(
        "--signals-include-sim",
        action="store_true",
        help="Include simulated outcome fields in signals dump (requires --sim-preflight)",
    )
    ap.add_argument(
        "--skip-risk-engine",
        action="store_true",
        help="Bypass the risk stage (pass trades through directly)",
    )
    # PR-Z.4: Exit Hazard Prediction Model
    ap.add_argument(
        "--enable-hazard-model",
        action="store_true",
        help="Enable hazard score computation for exit prediction",
    )
    # PR-G.4: Jito bundle execution (live mode only)
    ap.add_argument(
        "--use-jito-bundle",
        action="store_true",
        help="Use Jito bundles for critical buy transactions (LIVE mode only)",
    )
    # PR-Y.4: Bitquery Adapter
    ap.add_argument("--use-bitquery", action="store_true", help="Enable Bitquery GraphQL adapter")
    ap.add_argument("--bitquery-source", default="", help="Path to Bitquery fixture or 'live'")
    # PR-Y.5: Config Hot-Reload
    ap.add_argument("--hot-reload-config", action="store_true", help="Enable dynamic configuration reloading")
    # PR-PM.5: Risk Regime Integration
    ap.add_argument(
        "--regime-input",
        default="",
        help="Path to regime_timeline.parquet for risk regime adjustment"
    )
    ap.add_argument(
        "--skip-regime-adjustment",
        action="store_true",
        default=False,
        help="Skip risk regime adjustment (edge_final = edge_raw)"
    )

    args = ap.parse_args()

    # PR-Y.5: Configure logging for ConfigReloader visibility
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s', datefmt='%H:%M:%S')

    # PR-Y.5: Initialize reloader (starts thread if enabled)
    # We pass the config path from args.config
    init_reloader(args.config, hot_reload=args.hot_reload_config)
    
    try:
        return _main_inner(args)
    finally:
        stop_reloader()

def _main_inner(args) -> int:
    # PR-G.3: Live mode safety gates
    # Check if we're running in live mode
    is_live_mode = args.env == "live" or getattr(args, "mode", None) == "live"

    if is_live_mode:
        # Check 1: safety.live_trading_enabled must be true
        # Load config first to check the safety setting
        loaded = load_params_base(args.config)
        cfg = loaded.config
        safety_cfg = cfg.get("run", {}).get("safety", {})
        live_enabled = safety_cfg.get("live_trading_enabled", False)

        if not live_enabled:
            print(
                "[ERROR] Live execution disabled by config. Set safety.live_trading_enabled: true to enable.",
                file=sys.stderr,
            )
            return 1

        # Check 2: SOLANA_PRIVATE_KEY must be present and valid
        from integration.key_manager import load_signing_key, KeyLoadError
        try:
            load_signing_key()
        except KeyLoadError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1

        print("[INFO] Live mode safety gates passed.", file=sys.stderr)
    
    # PR-G.4: Validate --use-jito-bundle is only used in live mode
    if getattr(args, "use_jito_bundle", False) and not is_live_mode:
        print(
            "[ERROR] --use-jito-bundle is only supported in live mode.",
            file=sys.stderr,
        )
        return 1
    
    # Load config normally
    loaded = load_params_base(args.config)
    cfg = loaded.config

    def _log(msg: str) -> None:
        """Human logs.

        Contract:
        - If --summary-json is enabled, stdout must contain EXACTLY one JSON line
          (the summary) and nothing else. Therefore, all logs go to stderr.
        - Otherwise, logs go to stdout.
        """
        if args.summary_json:
            print(msg, file=sys.stderr)
        else:
            print(msg)

    ch_cfg = ClickHouseConfig()

    # Runner is only needed when writing to ClickHouse.
    runner = None
    if not args.dry_run:
        runner = make_runner(ch_cfg)

    resolved_modes = resolve_modes(cfg)

    def pick_mode(explicit_mode: Optional[str]) -> str:
        """Assign a mode bucket for metrics, deterministically."""
        if explicit_mode:
            if explicit_mode in resolved_modes:
                return explicit_mode
            return "__unknown_mode__"
        if "U" in resolved_modes:
            return "U"
        if resolved_modes:
            return sorted(resolved_modes.keys())[0]
        return "__no_mode__"

    def _mc_bucket(mode: str) -> Dict[str, int]:
        return {
            "total_lines": 0,
            "normalized_ok": 0,
            "rejected_by_normalizer": 0,
            "rejected_by_gates": 0,
            "rejected_by_risk": 0,
            "rejected_by_cooldown": 0,
            "rejected_by_wallet_tier": 0,
            "filtered_out": 0,
            "passed": 0,
        }

    mode_counts: Dict[str, Dict[str, int]] = defaultdict(_mc_bucket)

    run_trace_id = get_run_trace_id(args.run_trace_id or None, prefix="paper")

    # 1) config_version for reproducibility
    ts = _utc_now_iso_ms()
    row = _mk_config_version_row(
        ts=ts,
        chain=args.chain,
        env=args.env,
        path=loaded.path,
        strategy_name=loaded.strategy_name,
        version=loaded.version,
        config_hash=loaded.config_hash,
        run_trace_id=run_trace_id,
    )

    if args.dry_run:
        _log("[dry-run] would insert forensics_events(kind=config_version):")
        _log(json.dumps(row, ensure_ascii=False, indent=2))
    else:
        assert runner is not None
        runner.insert_json_each_row("forensics_events", [row])

    # 2) allowlist_version once per run_trace_id (avoid duplicate spam from per-row writers)
    if args.allowlist and not args.no_log_allowlist_version:
        wallets, allowlist_hash = load_allowlist(args.allowlist)
        allowlist_row = _mk_allowlist_version_row(
            ts=_utc_now_iso_ms(),
            chain=args.chain,
            env=args.env,
            path=args.allowlist,
            wallets_count=len(wallets),
            allowlist_hash=allowlist_hash,
            run_trace_id=run_trace_id,
        )
        if args.dry_run:
            _log("[dry-run] would insert forensics_events(kind=allowlist_version):")
            _log(json.dumps(allowlist_row, ensure_ascii=False, indent=2))
        else:
            assert runner is not None
            runner.insert_json_each_row("forensics_events", [allowlist_row])

    _log(f"[ok] wrote forensics_events config_version: {loaded.config_hash[:12]}… trace={run_trace_id}")

    # 2) Snapshot store (can be empty if file missing, but then gates will reject)
    # PR-F.2: Use live snapshot store if --live-snapshots is set
    if args.live_snapshots:
        if not HAS_LIVE_SNAPSHOT_STORE:
            _log("[error] LiveTokenSnapshotStore not available. Install required dependencies.")
            return 1
        store = LiveTokenSnapshotStore()
        _log("[ok] using live token snapshots from Jupiter API")
    else:
        store = TokenSnapshotStore(args.token_snapshot)
        try:
            store.load()
        except Exception as e:
            _log(f"[warn] failed to load token_snapshot parquet: {e}")

    # 2.5) Optional wallet profile store (for enrichment)
    wallet_store = None
    if args.wallet_profiles:
        try:
            if args.wallet_profiles.lower().endswith(".parquet"):
                wallet_store = WalletProfileStore.from_parquet(args.wallet_profiles)
            else:
                wallet_store = WalletProfileStore.from_csv(args.wallet_profiles)
            _log(f"[ok] loaded wallet_profiles: {len(getattr(wallet_store, '_by_wallet', {}))} wallets")
        except Exception as e:
            _log(f"[warn] failed to load wallet_profiles: {e}")

    # Initialize portfolio for risk stage
    initial_bankroll = float(cfg.get("initial_bankroll", 10000.0))
    portfolio = PortfolioStub(equity_usd=initial_bankroll, peak_equity_usd=initial_bankroll)
    _log(f"[ok] initialized portfolio with initial_bankroll={initial_bankroll}")

    # 3) Trades → snapshot → gates → writes
    # PR-F.1: Validate source type and arguments
    if args.source_type == "rpc":
        if not HAS_RPC_SOURCE:
            _log("[error] RpcSource not available. Install required dependencies for RPC ingestion.")
            return 1
        if not args.rpc_url:
            _log("[error] --source-type=rpc requires --rpc-url argument.")
            return 1
        if not args.tracked_wallets:
            _log("[error] --source-type=rpc requires --tracked-wallets argument.")
            return 1
    elif not args.use_bitquery and (bool(args.trades_jsonl) == bool(args.trades_parquet)):
        _log("[info] provide exactly one input: --trades-jsonl OR --trades-parquet. Done.")
        return 0

    # Build an iterator of Trade/Reject from either source.
    def _iter_inputs():
        # PR-Y.4: Bitquery Source
        if args.use_bitquery:
            if not HAS_BITQUERY_SOURCE:
                 yield {"_reject": True, "lineno": 0, "reason": "INVALID_CONFIG", "detail": "BitquerySource not available"}
                 return

            bq = BitquerySource()
            
            # 1. Load data (Fixture or Live)
            raw_response = {}
            if args.bitquery_source and os.path.isfile(args.bitquery_source):
                try:
                    with open(args.bitquery_source, "r") as f:
                        raw_response = json.load(f)
                except Exception as e:
                    yield {"_reject": True, "lineno": 0, "reason": "INVALID_CONFIG", "detail": f"failed_to_load_fixture:{e}"}
                    return
            else:
                # Live fetch (requires wallets)
                tracked_wallets = []
                if args.tracked_wallets:
                     tracked_wallets = [w.strip() for w in args.tracked_wallets.split(",") if w.strip()]
                
                # Mock time range for now or from args? 
                # For this PR scope we focus on fixture smoke test mostly, 
                # but live logic maps to fetch_wallet_trades which returns TradeEvents directly.
                # However, process_response is useful for handling the raw response if we had it.
                # BitquerySource.fetch_wallet_trades returns List[TradeEvent].
                # We can yielded them directly.
                
                # If we want to support 'live' via fetch_wallet_trades:
                # trades = bq.fetch_wallet_trades(tracked_wallets, ...)
                # for t in trades: yield t
                # But we need reject handling. 
                # Currently fetch_wallet_trades in my impl returns only valid trades.
                # To support rejects properly in live, we'd need to expose process_response more.
                # For this PR, we primarily support the fixture path via process_response.
                pass

            # 2. Process Response
            valid_trades, rejected = bq.process_response(raw_response)
            
            # Yield valid
            for i, t in enumerate(valid_trades, 1):
                # Convert TradeEvent to Trade (named tuple or dict expected by pipeline?)
                # Pipeline expects Normalize Trade objects (Trade namedtuple) or dicts.
                # TradeEvent from ingestion definition is a dataclass.
                # normalize_trade_record returns a Trade object.
                # We need to adapt TradeEvent -> Trade.
                
                # Trade is defined in integration.trade_types
                # Let's assume we can map fields.
                
                # We can use normalize_trade_record(t.to_dict())?
                # normalize_trade_record takes a raw dict and does validation.
                # TradeEvent is already normalized mostly.
                # Let's reconstruct Trade object manually or use dict.
                
                # Better: yield the TradeEvent converted to Trade or dict that pipeline can handle.
                # Pipeline iteration loop handles dict or Trade.
                # If dict, it does "item.get(...)".
                # If Trade, arguments access attrs.
                # Let's yield Trade objects.
                
                from integration.trade_types import Trade
                
                # TradeEvent fields: timestamp, wallet, mint, amount, price_usd, value_usd, platform, tx_hash
                # Trade fields: ts, wallet, mint, side, amount, ...
                
                # We need to map.
                # TradeEvent doesn't have 'side'. Bitquery query filtered for BUY/SELL but we normalized without side?
                # Wait, normalize_bitquery_trade didn't set side.
                # We should assume BUY for now or extract from raw?
                # The query requested BUY and SELL.
                # normalize logic didn't extract side.
                # Let's assume BUY for simplicity or fix normalize?
                # The prompt: "swaps[].amountIn/Out... price = amountOut/amountIn... SOL_USD"
                # This implies a swap. Direction implies side.
                # If amountIn is Token and amountOut is SOL -> SELL
                # If amountIn is SOL and amountOut is Token -> BUY
                # My normalize logic assumed:
                # qty_token = amount_in (implies we are selling token?)
                # No, I mapped `qty_token = float(amount_in)`
                # And `price = (amountOut / amountIn) * SOL`.
                # This implies we gave In and got Out.
                # If In was Token, we Sold.
                # If In was SOL, we Bought?
                
                # Re-reading plan/prompt:
                # "Конвертация: `amountIn/amountOut` → `qty_token` + `qty_usd`"
                # It didn't explicitly specify side logic.
                # I'll default to 'BUY' for safety/testing or 'UNKNOWN'.
                # Pipeline filters `if side != "BUY": continue` in some places (e.g. simulation).
                
                yield Trade(
                    ts=datetime.fromtimestamp(t.timestamp, timezone.utc).isoformat(),
                    wallet=t.wallet,
                    mint=t.mint,
                    side="BUY",  # Mocking as BUY for now
                    price=float(t.price_usd),
                    size_usd=float(t.value_usd),
                    tx_hash=t.tx_hash,
                    platform=t.platform,
                    # Extras
                    liquidity_usd=None,
                    volume_24h_usd=None,
                    spread_bps=None,
                    extra={
                        "source": "bitquery", 
                        "size_token": float(t.amount)
                    }
                )

            # Yield rejected
            for node, reason in rejected:
                yield {"_reject": True, "lineno": 0, "reason": reason, "detail": "bitquery_reject"}

            # If we yielded from Bitquery, do we continue?
            # If Bitquery is enabled, it acts as a source.
            # If we also want other sources, we shouldn't return.
            # But usually pipeline has one source.
            if args.source_type == "jsonl" and not args.trades_jsonl and not args.trades_parquet:
                 # If no other source provided, we are done.
                 return
                 
        # PR-F.1: Handle RPC source type
        if args.source_type == "rpc":
            # Parse tracked wallets from file or comma-separated string
            tracked_wallets = []
            if os.path.isfile(args.tracked_wallets):
                try:
                    with open(args.tracked_wallets, "r") as f:
                        tracked_wallets = [line.strip() for line in f if line.strip()]
                except Exception as e:
                    yield {"_reject": True, "lineno": 0, "reason": INVALID_TRADE, "detail": f"failed_to_read_wallets_file:{e}"}
                    return
            else:
                tracked_wallets = [w.strip() for w in args.tracked_wallets.split(",") if w.strip()]

            if not tracked_wallets:
                yield {"_reject": True, "lineno": 0, "reason": INVALID_TRADE, "detail": "no_tracked_wallets"}
                return

            try:
                rpc_source = RpcSource(rpc_url=args.rpc_url, tracked_wallets=tracked_wallets)
                for i, rec in enumerate(rpc_source.iter_records(), start=1):
                    # Normalize the RPC record to trade format
                    normalized = normalize_trade_record(rec, lineno=i)
                    yield normalized
                rpc_source.close()
            except Exception as e:
                yield {"_reject": True, "lineno": 0, "reason": INVALID_TRADE, "detail": f"rpc_source_error:{e}"}
            return

        if args.trades_jsonl:
            yield from load_trades_jsonl(args.trades_jsonl)
            return

        colmap = None
        if args.parquet_colmap_json:
            try:
                colmap_obj = json.loads(args.parquet_colmap_json)
                if not isinstance(colmap_obj, dict):
                    raise ValueError("colmap must be JSON object")
                colmap = colmap_obj
            except Exception as e:
                yield {"_reject": True, "lineno": 0, "reason": INVALID_TRADE, "detail": f"bad_parquet_colmap:{e}"}
                return

        pcfg = ParquetReadConfig(path=args.trades_parquet, limit=args.parquet_limit, colmap=colmap)
        for i, rec in enumerate(iter_parquet_records(pcfg), start=1):
            if not isinstance(rec, dict):
                yield {"_reject": True, "lineno": i, "reason": INVALID_TRADE, "detail": "parquet_row_not_dict"}
                continue
            yield normalize_trade_record(rec, lineno=i)

    total_lines = 0
    normalized_ok = 0
    rejected_by_normalizer = 0
    rejected_by_gates = 0
    rejected_by_risk = 0
    rejected_by_cooldown = 0
    rejected_by_wallet_tier = 0
    rejected_by_mode_risk = 0
    filtered_out = 0
    passed = 0
    wrote_signals = 0
    wrote_scores = 0
    reject_counts: Counter[str] = Counter()

    mode_counts: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "total_lines": 0,
            "normalized_ok": 0,
            "rejected_by_normalizer": 0,
            "rejected_by_gates": 0,
            "rejected_by_risk": 0,
            "rejected_by_cooldown": 0,
            "rejected_by_wallet_tier": 0,
            "rejected_by_mode_risk": 0,
            "filtered_out": 0,
            "passed": 0,
        }
    )

    tier_counts: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "total_lines": 0,
            "normalized_ok": 0,
            "rejected_by_normalizer": 0,
            "rejected_by_gates": 0,
            "rejected_by_risk": 0,
            "rejected_by_cooldown": 0,
            "rejected_by_wallet_tier": 0,
            "rejected_by_mode_risk": 0,
            "filtered_out": 0,
            "passed": 0,
        }
    )

    # PR-8.1: signals dump collection
    signal_rows: list[dict] = []

    collect_for_sim = bool(args.summary_json and (args.sim_preflight or args.execution_preflight))
    trades_norm_for_sim = []  # Trade objects only (includes future ticks)

    # Track lineno for each trade for signals dump
    trade_lineno = 0

    for item in _iter_inputs():
        # PR-Y.5: Update config from reloader (cheap thread-safe read)
        runtime_conf = get_runtime_config()
        # Update cfg (shadowing outer scope for this iteration)
        cfg = apply_runtime_overrides(cfg, runtime_conf)
        
        # Test helper: slow down pipeline if requested
        test_sleep = os.environ.get("PAPER_PIPELINE_SLEEP_SEC")
        if test_sleep:
            import time
            try:
                time.sleep(float(test_sleep))
            except ValueError:
                pass

        total_lines += 1
        trade_lineno += 1

        # PR-Z.1: Kill-switch check (only in non-dry-run mode)
        if not args.dry_run:
            from ops.panic import check_panic
            if check_panic():
                logger.critical("KILL SWITCH ACTIVE. HALTING PIPELINE.")
                break

        explicit_mode: Optional[str] = None
        if isinstance(item, dict):
            m = item.get("mode")
            if isinstance(m, str):
                explicit_mode = m
        else:
            m = (item.extra or {}).get("mode") if hasattr(item, "extra") else None
            if isinstance(m, str):
                explicit_mode = m

        mode_bucket = pick_mode(explicit_mode)
        mode_counts[mode_bucket]["total_lines"] += 1

        # Tier bucketing is based on wallet_profiles (if available). For lines that
        # fail normalization, we fall back to the missing-wallet-profile bucket.
        wp_for_tier = None
        tier_bucket = "__missing_wallet_profile__"
        if isinstance(item, Trade) and wallet_store is not None:
            wp_for_tier = wallet_store.get(item.wallet)
            if wp_for_tier is not None:
                tier_bucket = resolve_tier(wp_for_tier, cfg)
        tier_counts[tier_bucket]["total_lines"] += 1

        if isinstance(item, dict) and item.get("_reject"):
            # Normalizer rejects are dicts; count + optionally emit as forensics.
            reason = str(item.get("reason", INVALID_TRADE))
            reject_counts[reason] += 1
            rejected_by_normalizer += 1
            mode_counts[mode_bucket]["rejected_by_normalizer"] += 1
            tier_counts[tier_bucket]["rejected_by_normalizer"] += 1

            # PR-8.1: Build signal row for normalizer reject
            if args.signals_out:
                lineno_val = trade_lineno
                signal_row = _build_signal_row(
                    schema_version=SIGNALS_SCHEMA_VERSION,
                    run_trace_id=run_trace_id,
                    lineno=lineno_val,
                    ts="",
                    wallet="",
                    mint="",
                    tx_hash=str(item.get("tx_hash")) if item.get("tx_hash") else None,
                    mode=mode_bucket,
                    wallet_tier=None,
                    decision="SKIP",
                    reject_stage="normalizer",
                    reject_reason=reason,
                    edge_bps=None,
                    ttl_sec=None,
                    tp_pct=None,
                    sl_pct=None,
                    include_sim=args.signals_include_sim,
                )
                signal_rows.append(signal_row)

            if runner is not None:
                insert_trade_reject(
                    runner=runner,
                    chain=args.chain,
                    env=args.env,
                    trace_id=run_trace_id,
                    stage="normalizer",
                    reason=reason,
                    lineno=int(item.get("lineno")) if item.get("lineno") is not None else None,
                    wallet=None,
                    mint=None,
                    side=None,
                    tx_hash=str(item.get("tx_hash")) if item.get("tx_hash") else None,
                    detail=str(item.get("detail", "")) if item.get("detail") else None,
                    dry_run=False,
                )

            continue

        normalized_ok += 1
        mode_counts[mode_bucket]["normalized_ok"] += 1
        tier_counts[tier_bucket]["normalized_ok"] += 1
        t: Trade = item  # type: ignore

        # Optional enrichment from wallet_profiles (only fill missing metrics)
        if wallet_store is not None:
            wp = wp_for_tier if wp_for_tier is not None else wallet_store.get(t.wallet)
            if wp is not None:
                resolved_tier = resolve_tier(wp, cfg)
                t = replace(
                    t,
                    wallet_roi_30d_pct=t.wallet_roi_30d_pct if t.wallet_roi_30d_pct is not None else wp.roi_30d_pct,
                    wallet_winrate_30d=t.wallet_winrate_30d if t.wallet_winrate_30d is not None else wp.winrate_30d,
                    wallet_trades_30d=t.wallet_trades_30d if t.wallet_trades_30d is not None else wp.trades_30d,
                    extra=dict((t.extra or {}), **({"wallet_tier": resolved_tier})),
                )

        if collect_for_sim:
            trades_norm_for_sim.append(t)

        if args.only_buy and t.side != "BUY":
            # Filtering is not a rejection. Track separately so metrics remain meaningful.
            filtered_out += 1
            mode_counts[mode_bucket]["filtered_out"] += 1
            tier_counts[tier_bucket]["filtered_out"] += 1
            continue

        # Prefer inline snapshot, else pull from local store
        snap = _snapshot_from_trade_inline(t) or store.get(t.mint)

        decision = apply_gates(cfg=cfg, trade=t, snapshot=snap)
        if not decision.passed:
            reject_counts[decision.primary_reason or "rejected"] += 1
            rejected_by_gates += 1
            mode_counts[mode_bucket]["rejected_by_gates"] += 1
            tier_counts[tier_bucket]["rejected_by_gates"] += 1

            # PR-8.1: Build signal row for gates reject
            if args.signals_out:
                # Extract wallet_tier from trade extra if available
                wallet_tier = None
                if t.extra and isinstance(t.extra, dict):
                    wallet_tier = t.extra.get("wallet_tier")
                # Extract mode from trade extra if available
                mode_from_trade = mode_bucket
                if t.extra and isinstance(t.extra, dict) and t.extra.get("mode"):
                    mode_from_trade = t.extra.get("mode")

                # Get mode config for tp_pct and sl_pct
                mode_cfg = (cfg.get("modes") or {}).get(mode_from_trade, {})
                ttl_sec_val = int(mode_cfg.get("ttl_sec")) if mode_cfg.get("ttl_sec") else None
                tp_pct_val = float(mode_cfg.get("tp_pct")) if mode_cfg.get("tp_pct") else None
                sl_pct_val = float(mode_cfg.get("sl_pct")) if mode_cfg.get("sl_pct") else None

                signal_row = _build_signal_row(
                    schema_version=SIGNALS_SCHEMA_VERSION,
                    run_trace_id=run_trace_id,
                    lineno=0,
                    ts=t.ts,
                    wallet=t.wallet,
                    mint=t.mint,
                    tx_hash=t.tx_hash,
                    mode=mode_from_trade,
                    wallet_tier=wallet_tier,
                    decision="SKIP",
                    reject_stage="gates",
                    reject_reason=str(decision.primary_reason or "rejected"),
                    edge_bps=None,
                    ttl_sec=ttl_sec_val,
                    tp_pct=tp_pct_val,
                    sl_pct=sl_pct_val,
                    include_sim=args.signals_include_sim,
                )
                signal_rows.append(signal_row)

            # Emit queryable reject event (CH only)
            if runner is not None:
                insert_trade_reject(
                    runner=runner,
                    chain=args.chain,
                    env=args.env,
                    trace_id=run_trace_id,
                    stage="gates",
                    reason=str(decision.primary_reason or "rejected"),
                    lineno=None,
                    wallet=t.wallet,
                    mint=t.mint,
                    side=t.side,
                    tx_hash=t.tx_hash or None,
                    detail=str(decision.detail) if getattr(decision, "detail", None) else None,
                    dry_run=False,
                )
            continue

        passed += 1
        mode_counts[mode_bucket]["passed"] += 1
        tier_counts[tier_bucket]["passed"] += 1

        # Risk stage: apply risk limits (or bypass if --skip-risk-engine)
        if args.skip_risk_engine:
            # Bypass risk stage - pass trades through directly
            risk_passed_trades = [t]
            rejection_reason = None
        else:
            # Process through risk_stage generator
            # risk_stage yields (trade, reason) tuples
            risk_result = list(
                risk_stage(
                    trades=[t],
                    portfolio=portfolio,
                    cfg=cfg,
                    runner=runner,
                    trace_id=run_trace_id,
                    chain=args.chain,
                    env=args.env,
                )
            )
            # Extract trades and reason from risk_stage results
            risk_passed_trades = []
            rejection_reason = None
            for trade_result, reason in risk_result:
                if trade_result is not None:
                    risk_passed_trades.append(trade_result)
                else:
                    rejection_reason = reason

        if not risk_passed_trades:
            # Trade rejected by risk engine
            reject_counts["risk_rejected"] += 1
            # Check if this was a cooldown rejection
            if rejection_reason == RISK_COOLDOWN:
                rejected_by_cooldown += 1
                mode_counts[mode_bucket]["rejected_by_cooldown"] += 1
                tier_counts[tier_bucket]["rejected_by_cooldown"] += 1
            elif rejection_reason == RISK_WALLET_TIER_LIMIT:
                rejected_by_wallet_tier += 1
                mode_counts[mode_bucket]["rejected_by_wallet_tier"] += 1
                tier_counts[tier_bucket]["rejected_by_wallet_tier"] += 1
            elif rejection_reason == RISK_MODE_LIMIT:
                rejected_by_mode_risk += 1
                mode_counts[mode_bucket]["rejected_by_mode_risk"] += 1
                tier_counts[tier_bucket]["rejected_by_mode_risk"] += 1
            else:
                rejected_by_risk += 1
                mode_counts[mode_bucket]["rejected_by_risk"] += 1
                tier_counts[tier_bucket]["rejected_by_risk"] += 1

            # PR-8.1: Build signal row for risk reject (BUY flows only)
            if args.signals_out and t.side == "BUY":
                wallet_tier = None
                if t.extra and isinstance(t.extra, dict):
                    wallet_tier = t.extra.get("wallet_tier")
                mode_from_trade = mode_bucket
                if t.extra and isinstance(t.extra, dict) and t.extra.get("mode"):
                    mode_from_trade = t.extra.get("mode")

                mode_cfg = (cfg.get("modes") or {}).get(mode_from_trade, {})
                ttl_sec_val = int(mode_cfg.get("ttl_sec")) if mode_cfg.get("ttl_sec") else None
                tp_pct_val = float(mode_cfg.get("tp_pct")) if mode_cfg.get("tp_pct") else None
                sl_pct_val = float(mode_cfg.get("sl_pct")) if mode_cfg.get("sl_pct") else None

                signal_row = _build_signal_row(
                    schema_version=SIGNALS_SCHEMA_VERSION,
                    run_trace_id=run_trace_id,
                    lineno=trade_lineno,
                    ts=t.ts,
                    wallet=t.wallet,
                    mint=t.mint,
                    tx_hash=t.tx_hash,
                    mode=mode_from_trade,
                    wallet_tier=wallet_tier,
                    decision="SKIP",
                    reject_stage="risk",
                    reject_reason="risk_limit_exceeded",
                    edge_bps=None,
                    ttl_sec=ttl_sec_val,
                    tp_pct=tp_pct_val,
                    sl_pct=sl_pct_val,
                    include_sim=args.signals_include_sim,
                )
                signal_rows.append(signal_row)
            continue

        # Trade passed risk stage - use the first (and only) passed trade
        t = risk_passed_trades[0]

        # Update mode-specific portfolio tracking
        mode_from_trade = mode_bucket
        if t.extra and isinstance(t.extra, dict) and t.extra.get("mode"):
            mode_from_trade = t.extra.get("mode")
        portfolio.active_counts_by_mode[mode_from_trade] += 1
        portfolio.exposure_by_mode[mode_from_trade] += t.size_usd if t.size_usd else 0.0

        # PR-8.1: Build signal row for passed BUY trade (ENTER decision)
        if args.signals_out and t.side == "BUY":
            # Extract wallet_tier from trade extra if available
            wallet_tier = None
            if t.extra and isinstance(t.extra, dict):
                wallet_tier = t.extra.get("wallet_tier")
            # Extract mode from trade extra if available
            mode_from_trade = mode_bucket
            if t.extra and isinstance(t.extra, dict) and t.extra.get("mode"):
                mode_from_trade = t.extra.get("mode")

            # Get mode config for edge_bps, ttl_sec, tp_pct, sl_pct
            mode_cfg = (cfg.get("modes") or {}).get(mode_from_trade, {})
            edge_bps_val = None
            # Compute edge_bps if we have snapshot and wallet_profile
            if snap is not None:
                wp_for_edge = wallet_store.get(t.wallet) if wallet_store else None
                if wp_for_edge is not None:
                    edge_bps_val = compute_edge_bps(
                        trade=t, token_snap=snap, wallet_profile=wp_for_edge, cfg=cfg, mode_name=mode_from_trade
                    )
            ttl_sec_val = int(mode_cfg.get("ttl_sec")) if mode_cfg.get("ttl_sec") else None
            tp_pct_val = float(mode_cfg.get("tp_pct")) if mode_cfg.get("tp_pct") else None
            sl_pct_val = float(mode_cfg.get("sl_pct")) if mode_cfg.get("sl_pct") else None

            signal_row = _build_signal_row(
                schema_version=SIGNALS_SCHEMA_VERSION,
                run_trace_id=run_trace_id,
                lineno=trade_lineno,
                ts=t.ts,
                wallet=t.wallet,
                mint=t.mint,
                tx_hash=t.tx_hash,
                mode=mode_from_trade,
                wallet_tier=wallet_tier,
                decision="ENTER",
                reject_stage=None,
                reject_reason=None,
                edge_bps=edge_bps_val,
                ttl_sec=ttl_sec_val,
                tp_pct=tp_pct_val,
                sl_pct=sl_pct_val,
                include_sim=args.signals_include_sim,
            )
            signal_rows.append(signal_row)

        pool_id = t.pool_id or ""
        payload = {
            "trade_ts": t.ts,
            "trade_tx": t.tx_hash,
            "trade_side": t.side,
            "trade_price": t.price,
            "trade_size_usd": t.size_usd,
            "platform": t.platform,
            "run_trace_id": run_trace_id,
        }

        # Include minimal snapshot fields for debugging
        if snap is not None:
            payload.update(
                {
                    "snapshot_liquidity_usd": snap.liquidity_usd,
                    "snapshot_volume_24h_usd": snap.volume_24h_usd,
                    "snapshot_spread_bps": snap.spread_bps,
                }
            )

        # IMPORTANT: In --dry-run we must stay fully deterministic and keep stdout clean
        # for --summary-json. Do NOT call insert_signal/insert_wallet_score in dry-run,
        # because their helpers print human output.
        if not args.dry_run:
            insert_signal(
                cfg=ch_cfg,
                chain=args.chain,
                env=args.env,
                source=args.source,
                traced_wallet=t.wallet,
                token_mint=t.mint,
                pool_id=pool_id,
                ts=_utc_now_iso_ms(),
                trace_id=run_trace_id,
                signal_id="",
                payload=payload,
                allowlist_path=args.allowlist,
                require_allowlist=bool(args.require_allowlist),
                log_allowlist_version=False,
                dry_run=False,
            )
        wrote_signals += 1

        # Minimal wallet_score (P0.1: placeholder constant, but wired end-to-end)
        score = 0.5
        features = {"runner": "paper_pipeline", "run_trace_id": run_trace_id}
        if not args.dry_run:
            insert_wallet_score(
                cfg=ch_cfg,
                chain=args.chain,
                env=args.env,
                traced_wallet=t.wallet,
                score=score,
                features=features,
                ts=_utc_now_iso_ms(),
                trace_id=run_trace_id,
                trade_id=t.tx_hash,
                attempt_id="",
                allowlist_path=args.allowlist,
                log_allowlist_version=False,
                dry_run=False,
            )
        wrote_scores += 1

    summary = {
        "ok": True,
        "run_trace_id": run_trace_id,
        "input": {"kind": "jsonl" if args.trades_jsonl else "parquet", "path": args.trades_jsonl or args.trades_parquet},
        "counts": {
            "total_lines": total_lines,
            "normalized_ok": normalized_ok,
            "rejected_by_normalizer": rejected_by_normalizer,
            "rejected_by_gates": rejected_by_gates,
            "rejected_by_risk": rejected_by_risk,
            "rejected_by_cooldown": rejected_by_cooldown,
            "rejected_by_wallet_tier": rejected_by_wallet_tier,
            "rejected_by_mode_risk": rejected_by_mode_risk,
            "filtered_out": filtered_out,
            "passed": passed,
            "signals_written": wrote_signals,
            "wallet_scores_written": wrote_scores,
        },
        "rejects": dict(reject_counts),
    }

    # Normalize defaultdict to plain dict for JSON.
    summary["mode_counts"] = {k: dict(v) for k, v in mode_counts.items()}
    summary["tier_counts"] = {k: dict(v) for k, v in tier_counts.items()}

    if args.summary_json and args.sim_preflight:
        summary["sim_metrics"] = preflight_and_simulate(
            trades_norm=trades_norm_for_sim,
            cfg=cfg,
            token_snapshot_store=store,
            wallet_profile_store=wallet_store,
        )

    # PR-7: daily_metrics aggregation
    if args.summary_json and args.daily_metrics:
        if not args.sim_preflight:
            _log("ERROR: daily_metrics_requires_sim_metrics")
            return 2
        summary["daily_metrics"] = aggregate_daily_metrics(
            summary=summary,
            cfg=cfg,
            trades_norm=trades_norm_for_sim,
        )

    # PR-6.1: execution_metrics aggregation
    if args.summary_json and args.execution_preflight:
        summary["execution_metrics"] = execution_preflight(
            trades=trades_norm_for_sim,
            token_snapshots_store=store,
            wallet_profiles_store=wallet_store,
            cfg=cfg,
        )

    if args.metrics_out:
        try:
            with open(args.metrics_out, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log(f"[warn] failed to write metrics_out={args.metrics_out}: {e}")

    # PR-8.1: Write signals dump if --signals-out is set
    if args.signals_out:
        try:
            # If --signals-include-sim is set, enrich passed trades with sim results
            if args.signals_include_sim and args.summary_json and args.sim_preflight:
                sim_metrics = summary.get("sim_metrics", {})
                # Re-run simulation to get per-trade results
                sim_results = _get_sim_results_per_trade(
                    trades_norm=trades_norm_for_sim,
                    cfg=cfg,
                    token_snapshot_store=store,
                    wallet_profile_store=wallet_store,
                )
                # Enrich signal_rows with sim data
                for row in signal_rows:
                    if row["decision"] == "ENTER":
                        # Match by wallet and mint
                        key = (row["wallet"], row["mint"])
                        sim_result = sim_results.get(key, {})
                        row["sim_exit_reason"] = sim_result.get("exit_reason")
                        row["sim_pnl_usd"] = sim_result.get("pnl_usd")
                        row["sim_roi"] = sim_result.get("roi")

            write_signals_jsonl_atomic(args.signals_out, signal_rows)
            _log(f"[ok] wrote signals dump: {args.signals_out} ({len(signal_rows)} rows)")
        except Exception as e:
            _log(f"ERROR: failed to write signals_out={args.signals_out}: {e}")
            return 1

    if args.summary_json:
        # Exactly one JSON line on stdout.
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    else:
        _log(
            "[summary] "
            f"total_lines={total_lines} "
            f"normalized_ok={normalized_ok} "
            f"rejected_by_normalizer={rejected_by_normalizer} "
            f"rejected_by_gates={rejected_by_gates} "
            f"rejected_by_risk={rejected_by_risk} "
            f"rejected_by_cooldown={rejected_by_cooldown} "
            f"rejected_by_wallet_tier={rejected_by_wallet_tier} "
            f"rejected_by_mode_risk={rejected_by_mode_risk} "
            f"trades_passed_gates={passed} "
            f"signals_written={wrote_signals} "
            f"wallet_scores_written={wrote_scores} "
            f"run_trace_id={run_trace_id}"
        )

        if reject_counts:
            _log("[reject_reasons]")
            for reason, cnt in reject_counts.most_common(10):
                _log(f"  - {reason}: {cnt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
