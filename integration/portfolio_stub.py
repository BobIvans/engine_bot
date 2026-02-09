"""integration/portfolio_stub.py

Minimal portfolio state model for paper/sim.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PortfolioStub:
    equity_usd: float
    peak_equity_usd: float
    open_positions: int = 0
    day_pnl_usd: float = 0.0
    consecutive_losses: int = 0
    cooldown_until: float = 0.0
    active_counts_by_tier: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    active_counts_by_mode: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    exposure_by_mode: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    exposure_by_token: Dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity_usd <= 0:
            return 0.0
        dd = (self.peak_equity_usd - self.equity_usd) / self.peak_equity_usd
        return max(0.0, dd * 100.0)
