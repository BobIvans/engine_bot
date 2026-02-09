"""integration/portfolio_manager.py - Stateful Portfolio Manager

Stateful wrapper for managing portfolio state in Paper/Live pipelines.
Holds current state and applies transitions on fill events.

This is NOT pure - it has side effects (state mutation) and is meant
for runtime use. For pure logic, use strategy/state_update.py.
"""

from __future__ import annotations

import copy
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.state import PortfolioState, StateUpdateParams
from strategy.state_update import (
    transition_on_entry,
    transition_on_exit,
    update_cooldown,
    apply_fill_event,
)


logger = logging.getLogger(__name__)


class PortfolioManager:
    """Manages portfolio state with persistence.
    
    Provides stateful operations for Paper and Live trading pipelines.
    Internally uses pure transition functions from state_update.py.
    
    Usage:
        manager = PortfolioManager(initial_bankroll=10000.0)
        manager.on_fill(fill_event)  # Applies transition
        state = manager.get_state()  # Returns copy for strategy
    """
    
    def __init__(
        self,
        initial_bankroll_usd: float = 10000.0,
        params: Optional[StateUpdateParams] = None,
        checkpoint_path: Optional[str] = None,
        now_ts: int = 0,
    ):
        """Initialize portfolio manager.
        
        Args:
            initial_bankroll_usd: Starting capital.
            params: State update parameters (uses defaults if None).
            checkpoint_path: Optional path to load/save state checkpoint.
            now_ts: Current timestamp for initial state.
        """
        self.params = params or StateUpdateParams()
        self.checkpoint_path = checkpoint_path
        
        # Load from checkpoint or create initial state
        if checkpoint_path and Path(checkpoint_path).exists():
            self._state = self._load_checkpoint()
            logger.info(f"Loaded state from checkpoint: bankroll=${self._state.bankroll_usd:.2f}")
        else:
            self._state = PortfolioState.initial(initial_bankroll_usd, now_ts)
            logger.info(f"Initialized new state: bankroll=${initial_bankroll_usd:.2f}")
    
    def on_fill(self, fill_event: Dict[str, Any]) -> Dict[str, Any]:
        """Process a fill event and update state.
        
        Args:
            fill_event: Fill event dict with fields:
                - signal_id: Unique identifier
                - side: "BUY" or "SELL"
                - token_mint: Token address
                - wallet_address: Source wallet
                - size_usd: Position size
                - price: Fill price
                - pnl_usd: For SELL only
                - ts: Timestamp
        
        Returns:
            Result dict with success status and updated state summary.
        """
        signal_id = fill_event.get("signal_id", "unknown")
        side = fill_event.get("side", "UNKNOWN")
        ts = fill_event.get("ts", 0)
        
        logger.info(f"Processing fill: {signal_id} {side} at ts={ts}")
        
        # Apply the fill event transition
        new_state, error = apply_fill_event(
            state=self._state,
            fill_event=fill_event,
            params=self.params,
        )
        
        if error:
            logger.warning(f"Fill failed: {error}")
            return {
                "success": False,
                "signal_id": signal_id,
                "error": error,
                "state": self._get_state_summary(),
            }
        
        # Update state
        self._state = new_state
        
        # Check/update cooldown
        self._state = update_cooldown(self._state, self.params, ts)
        
        # Save checkpoint if path configured
        if self.checkpoint_path:
            self._save_checkpoint()
        
        logger.info(f"Fill processed: bankroll=${self._state.bankroll_usd:.2f}, "
                   f"positions={self._state.open_position_count}, "
                   f"cooldown={self._state.cooldown_active}")
        
        return {
            "success": True,
            "signal_id": signal_id,
            "state": self._get_state_summary(),
        }
    
    def on_entry(
        self,
        signal_id: str,
        token_mint: str,
        wallet_address: str,
        size_usd: float,
        fill_price: float,
        ts: int,
    ) -> Dict[str, Any]:
        """Process a position entry directly.
        
        Convenience method for BUY events.
        """
        fill_event = {
            "signal_id": signal_id,
            "side": "BUY",
            "token_mint": token_mint,
            "wallet_address": wallet_address,
            "size_usd": size_usd,
            "price": fill_price,
            "ts": ts,
        }
        return self.on_fill(fill_event)
    
    def on_exit(
        self,
        signal_id: str,
        token_mint: str,
        wallet_address: str,
        exit_price: float,
        pnl_usd: float,
        ts: int,
    ) -> Dict[str, Any]:
        """Process a position exit directly.
        
        Convenience method for SELL events.
        """
        fill_event = {
            "signal_id": signal_id,
            "side": "SELL",
            "token_mint": token_mint,
            "wallet_address": wallet_address,
            "size_usd": 0,  # Not needed for exit
            "price": exit_price,
            "pnl_usd": pnl_usd,
            "ts": ts,
        }
        return self.on_fill(fill_event)
    
    def get_state(self) -> PortfolioState:
        """Get current state copy for strategy decisions.
        
        Returns a deep copy to prevent external mutation.
        """
        return copy.deepcopy(self._state)
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current state for logging/monitoring."""
        return self._get_state_summary()
    
    def is_cooldown_active(self) -> bool:
        """Check if trading is in cooldown."""
        return self._state.cooldown_active
    
    def get_open_positions(self) -> Dict[str, Any]:
        """Get all open positions."""
        return {
            pos_id: {
                "token_mint": p.token_mint,
                "entry_price": p.entry_price,
                "size_usd": p.size_usd,
                "wallet_address": p.wallet_address,
                "opened_at": p.opened_at,
            }
            for pos_id, p in self._state.open_positions.items()
        }
    
    def can_open_position(self) -> tuple:
        """Check if a new position can be opened.
        
        Returns:
            (can_open: bool, reason: str)
        """
        from strategy.state import can_open_position
        return can_open_position(self._state, self.params)
    
    def reset_daily_pnl(self, ts: int) -> None:
        """Reset daily PnL counter (call at start of new trading day)."""
        from strategy.state_update import reset_daily_pnl
        self._state = reset_daily_pnl(self._state, ts)
        logger.info("Daily PnL reset")
        if self.checkpoint_path:
            self._save_checkpoint()
    
    def _get_state_summary(self) -> Dict[str, Any]:
        """Get internal state summary dict."""
        return {
            "bankroll_usd": self._state.bankroll_usd,
            "daily_pnl_usd": self._state.daily_pnl_usd,
            "total_drawdown_pct": self._state.total_drawdown_pct,
            "open_position_count": self._state.open_position_count,
            "cooldown_active": self._state.cooldown_active,
            "total_exposure": self._state.get_total_exposure(),
        }
    
    def _save_checkpoint(self) -> None:
        """Save state to checkpoint file."""
        if not self.checkpoint_path:
            return
        
        try:
            with open(self.checkpoint_path, "w") as f:
                json.dump(self._state.to_dict(), f, indent=2)
            logger.debug(f"Saved checkpoint to {self.checkpoint_path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def _load_checkpoint(self) -> PortfolioState:
        """Load state from checkpoint file."""
        if not self.checkpoint_path:
            raise FileNotFoundError(f"No checkpoint at {self.checkpoint_path}")
        
        with open(self.checkpoint_path, "r") as f:
            data = json.load(f)
        
        return PortfolioState.from_dict(data)


# Example usage and self-test
if __name__ == "__main__":
    import sys
    
    # Create manager with no checkpoint
    manager = PortfolioManager(initial_bankroll_usd=10000.0)
    params = StateUpdateParams(max_daily_loss_usd=500.0)
    
    print("=== Portfolio Manager Self-Test ===\n")
    
    print("Initial State:")
    state = manager.get_state()
    print(f"  Bankroll: ${state.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${state.daily_pnl_usd:.2f}")
    print(f"  Positions: {state.open_position_count}")
    print()
    
    # Test 1: Entry
    print("Test 1: Entry (BUY $1000 SOL)")
    result = manager.on_entry(
        signal_id="TRADE001",
        token_mint="SOLabc123",
        wallet_address="WalletA",
        size_usd=1000.0,
        fill_price=0.0002,
        ts=1001,
    )
    print(f"  Result: {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f"  Error: {result.get('error', 'N/A')}")
    state = manager.get_state()
    print(f"  Bankroll: ${state.bankroll_usd:.2f}")
    print(f"  Positions: {state.open_position_count}")
    print()
    
    # Test 2: Exit with profit
    print("Test 2: Exit with Profit (+$250)")
    result = manager.on_exit(
        signal_id="TRADE001",
        token_mint="SOLabc123",
        wallet_address="WalletA",
        exit_price=0.00025,
        pnl_usd=250.0,
        ts=1002,
    )
    print(f"  Result: {'SUCCESS' if result['success'] else 'FAILED'}")
    state = manager.get_state()
    print(f"  Bankroll: ${state.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${state.daily_pnl_usd:.2f}")
    print(f"  Cooldown: {state.cooldown_active}")
    print()
    
    # Test 3: Loss triggering cooldown
    print("Test 3: Loss triggering Cooldown (-$600)")
    manager2 = PortfolioManager(initial_bankroll_usd=10000.0)
    
    # Entry
    manager2.on_entry("TRADE002", "RAYxyz789", "WalletB", 1000.0, 0.001, ts=1003)
    
    # Exit with loss exceeding $500 daily limit
    result = manager2.on_exit(
        signal_id="TRADE002",
        token_mint="RAYxyz789",
        wallet_address="WalletB",
        exit_price=0.0005,
        pnl_usd=-600.0,
        ts=1004,
    )
    print(f"  Result: {'SUCCESS' if result['success'] else 'FAILED'}")
    state = manager2.get_state()
    print(f"  Bankroll: ${state.bankroll_usd:.2f}")
    print(f"  Daily PnL: ${state.daily_pnl_usd:.2f}")
    print(f"  Cooldown Active: {state.cooldown_active}")
    print()
    
    # Test 4: Cooldown prevents new entries
    print("Test 4: Cooldown blocks new entries")
    can_open, reason = manager2.can_open_position()
    print(f"  Can open position: {can_open}")
    print(f"  Reason: {reason}")
    print()
    
    print("=== All tests completed ===")
