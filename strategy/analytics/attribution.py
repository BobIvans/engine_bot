"""
Pure logic for Performance Attribution Analysis.

Decomposes PnL into components to understand profit/loss sources:
- Theoretical PnL: Ideal profit if entered at signal price
- Execution Drag: Cost of slippage and execution delays
- Fee Drag: Transaction fees and commissions

Answers: "Are we losing money from bad model or bad execution?"

Output format: pnl_attribution.v1.json
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class AttributionComponents:
    """PnL decomposition for a single trade."""
    trade_id: str
    side: str  # "buy" or "sell"
    qty: float
    
    # Price points
    price_signal: float
    price_entry: float
    price_exit: float
    
    # Calculated components
    theoretical_pnl: float
    execution_drag: float
    fee_drag: float
    net_pnl: float
    
    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "side": self.side,
            "qty": self.qty,
            "theoretical_pnl": round(self.theoretical_pnl, 6),
            "execution_drag": round(self.execution_drag, 6),
            "fee_drag": round(self.fee_drag, 6),
            "net_pnl": round(self.net_pnl, 6),
        }


@dataclass
class AttributionReport:
    """Aggregated attribution report for a batch of trades."""
    total_trades: int
    total_theoretical_pnl: float
    total_execution_drag: float
    total_fee_drag: float
    total_net_pnl: float
    
    # Percentages
    execution_drag_pct: float  # % of theoretical eaten by execution
    fee_drag_pct: float  # % of theoretical eaten by fees
    
    trades: List[AttributionComponents] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "version": "pnl_attribution.v1",
            "total_trades": self.total_trades,
            "total_theoretical_pnl": round(self.total_theoretical_pnl, 6),
            "total_execution_drag": round(self.total_execution_drag, 6),
            "total_fee_drag": round(self.total_fee_drag, 6),
            "total_net_pnl": round(self.total_net_pnl, 6),
            "execution_drag_pct": round(self.execution_drag_pct, 2),
            "fee_drag_pct": round(self.fee_drag_pct, 2),
        }


def get_side_sign(side: str) -> int:
    """Get multiplier for side direction (+1 for buy, -1 for sell)."""
    return 1 if side.lower() == "buy" else -1


def decompose_trade(trade: Dict[str, Any]) -> AttributionComponents:
    """
    Decompose a single trade into PnL components.
    
    Args:
        trade: Trade dict with required fields:
            - trade_id (optional, defaults to "unknown")
            - side: "buy" or "sell"
            - qty: quantity
            - price_signal: signal/trigger price
            - price_entry: actual entry price
            - price_exit: actual exit price
            - fees_total: total fees paid
    
    Returns:
        AttributionComponents with calculated PnL breakdown
    
    Formula for BUY:
        Theoretical PnL = (exit - signal) * qty  [profit if exit > signal]
        Execution Drag = (entry - signal) * qty  [cost if entry > signal]
        Net PnL = Theoretical - Execution Drag - Fees
        
    Formula for SELL (short):
        Theoretical PnL = (signal - exit) * qty  [profit if signal > exit]
        Execution Drag = (signal - entry) * qty  [cost if signal > entry]
    """
    trade_id = trade.get("trade_id", "unknown")
    side = trade.get("side", "buy")
    qty = float(trade.get("qty", 0))
    
    price_signal = float(trade.get("price_signal", 0))
    price_entry = float(trade.get("price_entry", 0))
    price_exit = float(trade.get("price_exit", 0))
    fees_total = float(trade.get("fees_total", 0))
    
    side_sign = get_side_sign(side)
    
    # Theoretical PnL: what we would have made if entered at signal price
    theoretical_pnl = (price_exit - price_signal) * qty * side_sign
    
    # Execution Drag: cost of entering at worse price than signal
    # For buy: if entry > signal, we paid more (negative drag)
    # For sell: if entry < signal, we sold cheaper (negative drag)
    execution_drag = (price_entry - price_signal) * qty * side_sign
    
    # Fee Drag: direct fee costs
    fee_drag = fees_total
    
    # Net PnL: what we actually made
    net_pnl = theoretical_pnl - execution_drag - fee_drag
    
    return AttributionComponents(
        trade_id=trade_id,
        side=side,
        qty=qty,
        price_signal=price_signal,
        price_entry=price_entry,
        price_exit=price_exit,
        theoretical_pnl=theoretical_pnl,
        execution_drag=execution_drag,
        fee_drag=fee_drag,
        net_pnl=net_pnl,
    )


def aggregate_attribution(components: List[AttributionComponents]) -> AttributionReport:
    """
    Aggregate attribution components into a summary report.
    
    Args:
        components: List of per-trade attribution breakdowns
        
    Returns:
        AttributionReport with totals and percentages
    """
    if not components:
        return AttributionReport(
            total_trades=0,
            total_theoretical_pnl=0.0,
            total_execution_drag=0.0,
            total_fee_drag=0.0,
            total_net_pnl=0.0,
            execution_drag_pct=0.0,
            fee_drag_pct=0.0,
            trades=[],
        )
    
    total_theoretical = sum(c.theoretical_pnl for c in components)
    total_exec_drag = sum(c.execution_drag for c in components)
    total_fee_drag = sum(c.fee_drag for c in components)
    total_net = sum(c.net_pnl for c in components)
    
    # Calculate percentages (of theoretical PnL eaten by drags)
    if abs(total_theoretical) > 0.0001:
        exec_drag_pct = (total_exec_drag / total_theoretical) * 100
        fee_drag_pct = (total_fee_drag / total_theoretical) * 100
    else:
        exec_drag_pct = 0.0
        fee_drag_pct = 0.0
    
    return AttributionReport(
        total_trades=len(components),
        total_theoretical_pnl=total_theoretical,
        total_execution_drag=total_exec_drag,
        total_fee_drag=total_fee_drag,
        total_net_pnl=total_net,
        execution_drag_pct=exec_drag_pct,
        fee_drag_pct=fee_drag_pct,
        trades=components,
    )


def format_output(report: AttributionReport) -> dict:
    """Format attribution report for JSON output."""
    return report.to_dict()


if __name__ == "__main__":
    # Simple test matching smoke test expectations
    import json
    
    trade = {
        "trade_id": "test_001",
        "side": "buy",
        "qty": 1.0,
        "price_signal": 100.0,
        "price_entry": 101.0,
        "price_exit": 110.0,
        "fees_total": 0.5,
    }
    
    components = decompose_trade(trade)
    print(f"Theoretical PnL: {components.theoretical_pnl}")  # Expected: 10.0
    print(f"Execution Drag: {components.execution_drag}")    # Expected: 1.0
    print(f"Fee Drag: {components.fee_drag}")                # Expected: 0.5
    print(f"Net PnL: {components.net_pnl}")                  # Expected: 8.5
    
    report = aggregate_attribution([components])
    print(json.dumps(report.to_dict(), indent=2))
