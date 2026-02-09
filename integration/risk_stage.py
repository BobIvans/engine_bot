"""integration/risk_stage.py

Risk stage iterator - glue code connecting risk engine to the pipeline.

This stage applies P0 risk limits to each trade:
- Kill-switch on daily loss threshold
- Max open positions check
- Cooldown check
- Wallet tier limits check

Yields (Trade, None) for allowed trades and (None, reason) for rejections.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional, Tuple, Union

from integration.portfolio_stub import PortfolioStub
from integration.trade_types import Trade
from integration.write_trade_reject import insert_trade_reject
from strategy.risk_engine import apply_risk_limits


def risk_stage(
    trades: Iterator[Trade],
    portfolio: PortfolioStub,
    cfg: Dict[str, Any],
    runner: Optional[Any],  # ClickHouse runner or None
    trace_id: str,
    chain: str,
    env: str,
) -> Iterator[Tuple[Optional[Trade], Optional[str]]]:
    """Apply risk limits to trades.

    Args:
        trades: Iterator of trades to process
        portfolio: Current portfolio state (mutable, updated for allowed trades)
        cfg: Strategy configuration dict
        runner: ClickHouse runner for logging rejections (can be None)
        trace_id: Run trace identifier
        chain: Blockchain network (e.g., 'solana')
        env: Environment (e.g., 'paper', 'prod')

    Yields:
        Tuple of (Trade, None) for allowed trades
        Tuple of (None, reason) for rejected trades

    Side Effects:
        - Updates portfolio.open_positions for each allowed trade
        - Updates portfolio.active_counts_by_tier for allowed trades by tier
        - Logs rejected trades to ClickHouse (if runner available)
    """
    reject_count = 0

    for trade in trades:
        # Apply risk limits with None for signal (not used in P0)
        allowed, reason = apply_risk_limits(
            trade=trade,
            signal=None,
            portfolio=portfolio,
            cfg=cfg,
        )

        if allowed:
            # Mock update for P0 paper stream
            portfolio.open_positions += 1
            
            # Update tier count if tier is known
            if hasattr(trade, 'extra') and trade.extra:
                tier = trade.extra.get('wallet_tier')
                if tier:
                    portfolio.active_counts_by_tier[tier] += 1
                
                # Update mode counts and exposure
                mode = trade.extra.get('mode', 'U')
                portfolio.active_counts_by_mode[mode] += 1
                if hasattr(trade, 'size_usd') and trade.size_usd is not None:
                    portfolio.exposure_by_mode[mode] += trade.size_usd
            
            yield trade, None
        else:
            # Log rejection to ClickHouse
            dry_run = runner is None
            insert_trade_reject(
                runner=runner,
                chain=chain,
                env=env,
                trace_id=trace_id,
                stage="risk",
                reason=reason or "unknown",
                lineno=None,
                wallet=trade.wallet if hasattr(trade, "wallet") else None,
                mint=trade.mint if hasattr(trade, "mint") else None,
                side=trade.side if hasattr(trade, "side") else None,
                tx_hash=trade.tx_hash if hasattr(trade, "tx_hash") else None,
                detail=None,
                dry_run=dry_run,
            )
            reject_count += 1
            yield None, reason
