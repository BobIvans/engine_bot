"""integration/realtime_runner.py

PR-D.2 Realtime Paper Runner Loop.

Orchestrates continuous processing of live trades from RPC source:
- Poll new records from tracked wallets
- Normalize trades
- Apply signal engine (gates + edge)
- Apply risk limits
- Execute paper trades (mock)
- Write signals/forensics to ClickHouse

Design goals:
- Clean stdout (logs to stderr)
- Deterministic in smoke tests (mock source)
- Graceful error handling with retry
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from integration.config_loader import load_params_base
from integration.gates import apply_gates
from integration.portfolio_stub import PortfolioStub
from integration.reject_reasons import assert_reason_known
from integration.sim_preflight import compute_edge_bps
from integration.token_snapshot_store import TokenSnapshot
from integration.trade_types import Trade
from integration.helpers import write_signal
from strategy.signal_engine import decide_entry


@dataclass
class RealtimeRunner:
    """Orchestrates realtime copy-trade processing.

    Attributes:
        config: Strategy configuration dict.
        source: TradeSource for polling new records.
        snapshot_store: TokenSnapshot provider for enrichment.
        portfolio: Portfolio state (persists across iterations).
        last_signatures: Dict[wallet -> last_processed_signature].
        interval_sec: Poll interval in seconds.
    """

    config: Dict[str, Any]
    source: Any  # TradeSource interface
    snapshot_store: Any  # TokenSnapshot provider
    portfolio: PortfolioStub = field(default_factory=lambda: PortfolioStub(
        equity_usd=10000.0,
        peak_equity_usd=10000.0,
    ))
    last_signatures: Dict[str, str] = field(default_factory=dict)
    interval_sec: int = 5

    def run_loop(self, max_iterations: Optional[int] = None) -> None:
        """Run the main processing loop.

        Args:
            max_iterations: Optional limit on iterations (for smoke tests).
        """
        iteration = 0
        tracked_wallets = self.config.get("tracked_wallets", [])

        if not tracked_wallets:
            print("[RealtimeRunner] No tracked wallets configured", file=sys.stderr)
            return

        print(f"[RealtimeRunner] Starting loop for {len(tracked_wallets)} wallets", file=sys.stderr)

        while True:
            iteration += 1
            if max_iterations is not None and iteration > max_iterations:
                print(f"[RealtimeRunner] Reached max iterations ({max_iterations})", file=sys.stderr)
                break

            for wallet in tracked_wallets:
                self._process_wallet(wallet)

            time.sleep(self.interval_sec)

    def _process_wallet(self, wallet: str) -> None:
        """Process new records for a single wallet."""
        last_sig = self.last_signatures.get(wallet)

        try:
            records = self.source.poll_new_records(
                wallet=wallet,
                stop_at_signature=last_sig,
                limit=50,
            )
        except Exception as e:
            print(f"[RealtimeRunner] RPC error for {wallet}: {e}", file=sys.stderr)
            time.sleep(1)
            return

        if not records:
            return

        # Update last signature to the most recent processed
        self.last_signatures[wallet] = records[-1].get("tx_hash", "")

        for record in records:
            self._process_trade(record)

    def _process_trade(self, record: Dict[str, Any]) -> None:
        """Process a single trade record."""
        # Normalize record to Trade
        trade = self._normalize_trade(record)
        if trade is None:
            return

        print(f"[RealtimeRunner] Processing trade {trade.tx_hash[:8]}... {trade.side} {trade.mint[:8]}", file=sys.stderr)

        # Get token snapshot for enrichment
        snapshot = self._get_snapshot(trade.mint)

        # Apply signal engine
        signal = decide_entry(
            trade=trade,
            snapshot=snapshot,
            wallet_profile=None,
            cfg=self.config,
        )

        if not signal.should_enter:
            print(f"[RealtimeRunner] Signal rejected: {signal.reason}", file=sys.stderr)
            return

        # Apply risk limits
        allowed, reason = self._apply_risk_limits(trade, signal.mode)
        if not allowed:
            print(f"[RealtimeRunner] Risk rejected: {reason}", file=sys.stderr)
            return

        # Paper execution
        self._execute_paper_trade(trade, signal)

        # Write signal to ClickHouse
        try:
            write_signal(
                traced_wallet=trade.wallet,
                token_mint=trade.mint,
                pool_id=trade.pool_id,
                payload={
                    "signal": "entry",
                    "side": trade.side,
                    "price": trade.price,
                    "size_usd": trade.size_usd,
                    "mode": signal.mode,
                    "edge_bps": signal.edge_bps,
                    "reason": signal.reason,
                },
                dry_run=True,  # Paper mode
            )
        except Exception as e:
            print(f"[RealtimeRunner] Signal write error: {e}", file=sys.stderr)

    def _normalize_trade(self, record: Dict[str, Any]) -> Optional[Trade]:
        """Normalize raw record to Trade dataclass."""
        try:
            return Trade(
                ts=record.get("ts", str(int(time.time()))),
                wallet=record.get("wallet", ""),
                mint=record.get("mint", ""),
                side=record.get("side", "buy").upper(),
                price=float(record.get("price", 0.0)),
                size_usd=float(record.get("size_usd", 0.0)),
                platform=record.get("platform", ""),
                tx_hash=record.get("tx_hash", ""),
                pool_id=record.get("pool_id", ""),
                liquidity_usd=record.get("liquidity_usd"),
                volume_24h_usd=record.get("volume_24h_usd"),
                spread_bps=record.get("spread_bps"),
                honeypot_pass=record.get("honeypot_pass"),
                wallet_roi_30d_pct=record.get("wallet_roi_30d_pct"),
                wallet_winrate_30d=record.get("wallet_winrate_30d"),
                wallet_trades_30d=record.get("wallet_trades_30d"),
                extra=record.get("extra"),
            )
        except Exception as e:
            print(f"[RealtimeRunner] Normalization error: {e}", file=sys.stderr)
            return None

    def _get_snapshot(self, mint: str) -> Optional[TokenSnapshot]:
        """Get token snapshot from store."""
        try:
            return self.snapshot_store.get(mint)
        except Exception:
            return None

    def _apply_risk_limits(self, trade: Trade, mode: str) -> tuple[bool, Optional[str]]:
        """Apply risk engine limits to the trade."""
        # Mode-based position limits
        mode_limits = (self.config.get("risk") or {}).get("limits") or {}
        mode_limit = (mode_limits.get("mode_limits") or {}).get(mode, {}).get("max_open_positions")

        if mode_limit is not None:
            current_mode_count = self.portfolio.active_counts_by_mode.get(mode, 0)
            if current_mode_count >= mode_limit:
                reason = "RISK_MODE_LIMIT"
                assert_reason_known(reason)
                return False, reason

        # Max positions limit
        max_positions = (self.config.get("risk") or {}).get("limits", {}).get("max_open_positions")
        if max_positions is not None and self.portfolio.open_positions >= max_positions:
            reason = "RISK_MAX_POSITIONS"
            assert_reason_known(reason)
            return False, reason

        # Max exposure by token
        token_exposure = self.portfolio.exposure_by_token.get(trade.mint, 0.0)
        max_exposure = (self.config.get("risk") or {}).get("limits", {}).get("max_exposure_usd")
        if max_exposure is not None and token_exposure >= max_exposure:
            reason = "RISK_MAX_EXPOSURE"
            assert_reason_known(reason)
            return False, reason

        # Cooldown check
        if time.time() < self.portfolio.cooldown_until:
            reason = "RISK_COOLDOWN"
            assert_reason_known(reason)
            return False, reason

        return True, None

    def _execute_paper_trade(self, trade: Trade, signal) -> None:
        """Execute a paper trade (mock)."""
        size_usd = signal.calc_details.get("size_usd", trade.size_usd)

        print(f"PAPER EXECUTION: BUY {trade.mint[:8]}... {size_usd:.2f}USD @ {trade.price:.6f}", file=sys.stderr)

        # Update portfolio state
        self.portfolio.equity_usd -= size_usd
        self.portfolio.open_positions += 1
        self.portfolio.exposure_by_token[trade.mint] += size_usd

        mode = signal.mode
        self.portfolio.active_counts_by_mode[mode] += 1

        if self.portfolio.equity_usd > self.portfolio.peak_equity_usd:
            self.portfolio.peak_equity_usd = self.portfolio.equity_usd
