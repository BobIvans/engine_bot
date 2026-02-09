"""
Order Manager (PR-E.5)

Manages position lifecycle with TTL, TP, and SL monitoring.

HARD RULES:
- Only operates after successful fill (not at signal stage)
- TTL counts from fill moment (not signal)
- In --dry-run / paper mode: state changes only simulated
- All transitions logged with timestamp and reason
- Force close (TTL/TP/SL) must be idempotent
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from execution.order_state_machine import (
    PositionState,
    PositionStatus,
    CloseReason,
    CloseAction,
    OrderManagerConfig,
    log_transition,
)

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages position lifecycle with TTL and bracket orders.
    
    Usage:
        manager = OrderManager(
            executor=live_executor,
            config=OrderManagerConfig(),
            dry_run=False,
        )
        
        # On fill
        position = manager.on_fill(fill_event)
        
        # On tick (periodic)
        actions = await manager.on_tick(token_snapshot)
        
        # Force close
        action = manager.force_close(signal_id, "manual_close")
    """
    
    def __init__(
        self,
        executor: Optional[Any] = None,
        config: OrderManagerConfig = None,
        dry_run: bool = False,
    ):
        """
        Initialize the order manager.
        
        Args:
            executor: Live executor for executing closes (None for dry-run)
            config: Order manager configuration
            dry_run: If True, don't actually close positions
        """
        self.executor = executor
        self.config = config or OrderManagerConfig()
        self.dry_run = dry_run
        
        # Active positions
        self._positions: Dict[str, PositionState] = {}
        
        # Position history for debugging
        self._history: List[Dict[str, Any]] = []
    
    def on_fill(
        self,
        signal_id: str,
        mint: str,
        entry_price: float,
        size_usd: float,
        entry_ts: datetime,
        ttl_seconds: int,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> PositionState:
        """
        Register a new position after successful fill.
        
        Args:
            signal_id: Signal that triggered the trade
            mint: Token mint address
            entry_price: Filled price
            size_usd: Position size in USD
            entry_ts: Fill timestamp
            ttl_seconds: Time-to-live in seconds
            tp_price: Take-profit price (optional)
            sl_price: Stop-loss price (optional)
            
        Returns:
            PositionState for the new position.
        """
        # Check if position already exists (idempotency)
        if signal_id in self._positions:
            logger.warning(f"[order_mgr] Position {signal_id} already exists, skipping")
            return self._positions[signal_id]
        
        # Check max positions
        if len(self._positions) >= self.config.max_positions:
            logger.warning(
                f"[order_mgr] Max positions reached ({self.config.max_positions}), "
                f"cannot register new position {signal_id}"
            )
            raise RuntimeError("Max positions reached")
        
        # Calculate TTL expiration
        ttl_expires_at = entry_ts + timedelta(seconds=ttl_seconds)
        
        # Create position state
        position = PositionState(
            signal_id=signal_id,
            mint=mint,
            entry_price=entry_price,
            size_usd=size_usd,
            entry_ts=entry_ts,
            ttl_expires_at=ttl_expires_at,
            tp_price=tp_price,
            sl_price=sl_price,
            status=PositionStatus.ACTIVE,
            remaining_size_usd=size_usd,
        )
        
        self._positions[signal_id] = position
        
        logger.info(
            f"[order_mgr] Position opened: {signal_id} "
            f"mint={mint[:8]}... entry={entry_price} size={size_usd}"
        )
        
        return position
    
    async def on_tick(
        self,
        mint: str,
        current_price: float,
        current_ts: datetime,
        side: str = "BUY",
    ) -> List[CloseAction]:
        """
        Check all active positions on a price tick.
        
        Args:
            mint: Token mint address
            current_price: Current token price
            current_ts: Current timestamp
            side: Trade side (BUY/SELL)
            
        Returns:
            List of CloseAction to perform.
        """
        actions = []
        
        for signal_id, position in list(self._positions.items()):
            # Skip if not for this mint or already closed
            if position.mint != mint or not position.is_active:
                continue
            
            # Check TTL expiration
            if position.check_ttl(current_ts):
                action = self._create_close_action(
                    position,
                    CloseReason.TTL_EXPIRED.value,
                    current_price,
                )
                actions.append(action)
                continue
            
            # Check take-profit
            if position.check_tp(current_price, side):
                action = self._create_close_action(
                    position,
                    CloseReason.TP_HIT.value,
                    current_price,
                )
                actions.append(action)
                continue
            
            # Check stop-loss
            if position.check_sl(current_price, side):
                action = self._create_close_action(
                    position,
                    CloseReason.SL_HIT.value,
                    current_price,
                )
                actions.append(action)
                continue
        
        return actions
    
    def force_close(
        self,
        signal_id: str,
        reason: str,
        price: Optional[float] = None,
        size_usd: Optional[float] = None,
    ) -> Optional[CloseAction]:
        """
        Force close a position.
        
        Args:
            signal_id: Position to close
            reason: Reason for closure
            price: Optional close price
            size_usd: Optional size to close (partial)
            
        Returns:
            CloseAction if position was active, None otherwise.
        """
        position = self._positions.get(signal_id)
        
        if position is None or not position.is_active:
            logger.debug(f"[order_mgr] Force close: {signal_id} not active, skipping")
            return None
        
        # Create close action
        action = self._create_close_action(
            position,
            reason,
            price or position.entry_price,
            size_usd,
        )
        
        return action
    
    def _create_close_action(
        self,
        position: PositionState,
        reason: str,
        price: float,
        size_usd: Optional[float] = None,
    ) -> CloseAction:
        """
        Create and apply a close action.
        
        Args:
            position: Position to close
            reason: Reason for closure
            price: Close price
            size_usd: Size to close (None for full)
            
        Returns:
            CloseAction.
        """
        # Determine action type
        is_partial = (
            size_usd is not None and
            size_usd < position.remaining_size_usd
        )
        action_type = "PARTIAL_CLOSE" if is_partial else "CLOSE"
        
        # Update position state
        old_status = position.status
        
        if is_partial:
            position.status = PositionStatus.PARTIAL
            position.remaining_size_usd -= size_usd or 0
            position.close_reason = reason
            position.close_price = price
            position.close_ts = datetime.utcnow()
        else:
            position.status = PositionStatus.CLOSED
            position.close_reason = reason
            position.close_price = price
            position.close_ts = datetime.utcnow()
            
            # Remove from active positions
            del self._positions[position.signal_id]
        
        # Log transition
        new_status = position.status
        log_transition(position, old_status, new_status, reason)
        
        # Add to history
        self._history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "signal_id": position.signal_id,
            "action": action_type,
            "reason": reason,
            "price": price,
            "size_usd": size_usd or position.size_usd,
        })
        
        return CloseAction(
            signal_id=position.signal_id,
            action_type=action_type,
            reason=reason,
            price=price,
            size_usd=size_usd,
        )
    
    async def execute_close(self, action: CloseAction) -> bool:
        """
        Execute a close action through the executor.
        
        Args:
            action: CloseAction to execute.
            
        Returns:
            True if successful.
        """
        if self.dry_run:
            logger.info(
                f"[order_mgr] DRY-RUN: would close {action.signal_id} "
                f"({action.reason})"
            )
            return True
        
        if self.executor is None:
            logger.error("[order_mgr] No executor configured, cannot execute close")
            return False
        
        try:
            # Delegate to executor
            result = await self.executor.execute_close(
                signal_id=action.signal_id,
                reason=action.reason,
                price=action.price,
                size_usd=action.size_usd,
            )
            return result
        except Exception as e:
            logger.error(f"[order_mgr] Failed to execute close {action.signal_id}: {e}")
            return False
    
    def get_position(self, signal_id: str) -> Optional[PositionState]:
        """Get a position by signal ID."""
        return self._positions.get(signal_id)
    
    def get_active_positions(self) -> List[PositionState]:
        """Get all active positions."""
        return [p for p in self._positions.values() if p.is_active]
    
    def get_position_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent position history."""
        return self._history[-limit:]
    
    def export_positions(self) -> List[Dict[str, Any]]:
        """Export all positions as dictionaries."""
        return [p.to_dict() for p in self._positions.values()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get order manager statistics."""
        closed = [h for h in self._history if h["action"] == "CLOSE"]
        
        reasons = {}
        for h in closed:
            reason = h["reason"]
            reasons[reason] = reasons.get(reason, 0) + 1
        
        return {
            "active_positions": len(self.get_active_positions()),
            "total_closed": len(closed),
            "close_reasons": reasons,
            "max_positions": self.config.max_positions,
        }


# Mock executor for testing
class MockExecutor:
    """Mock executor for testing."""
    
    def __init__(self):
        self.closes: List[Dict[str, Any]] = []
    
    async def execute_close(
        self,
        signal_id: str,
        reason: str,
        price: float,
        size_usd: float,
    ) -> bool:
        self.closes.append({
            "signal_id": signal_id,
            "reason": reason,
            "price": price,
            "size_usd": size_usd,
        })
        return True


# Mock position for testing
def create_test_position(
    signal_id: str = "test-signal-001",
    mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    entry_price: float = 1.0,
    size_usd: float = 100.0,
    ttl_seconds: int = 3600,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> PositionState:
    """Create a test position."""
    return PositionState(
        signal_id=signal_id,
        mint=mint,
        entry_price=entry_price,
        size_usd=size_usd,
        entry_ts=datetime.utcnow(),
        ttl_expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds),
        tp_price=tp_price,
        sl_price=sl_price,
    )
