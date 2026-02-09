"""execution/partial_fill_handler.py

PR-G.5 Partial Fill Handler.

Handles partial fills and manages timeout-based resolution:
- Tracks filled_amount vs expected_amount
- Triggers force close or cancel on timeout
- Updates PortfolioState.exposure
- Logs all adjustments with trace_id/tx_sig

Usage:
    handler = PartialFillHandler(timeout_sec=60)
    handler.on_partial_fill(signal_id, filled_amount, tx_sig, trace_id)
    if handler.is_expired(signal_id):
        handler.force_close_remaining(signal_id)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PartialFill:
    """State for a partially filled order."""
    signal_id: str
    mint: str
    expected_amount: float
    filled_amount: float
    entry_price: float
    tx_sig: str
    trace_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"  # pending | completed | expired | closed


@dataclass
class FillAdjustment:
    """Adjustment record for partial fill resolution."""
    signal_id: str
    mint: str
    adjustment_type: str  # partial_fill | force_close | timeout_close | cancel
    tx_sig: str
    trace_id: str
    filled_amount: float
    remaining_amount: float
    price: float
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "mint": self.mint,
            "adjustment_type": self.adjustment_type,
            "tx_sig": self.tx_sig,
            "trace_id": self.trace_id,
            "filled_amount": self.filled_amount,
            "remaining_amount": self.remaining_amount,
            "price": self.price,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


class PartialFillHandler:
    """Handles partial fills with timeout-based resolution.
    
    Attributes:
        timeout_sec: Seconds before force-closing remaining amount
        max_retries: Maximum retry attempts for close
    """
    
    def __init__(
        self,
        timeout_sec: int = 60,
        max_retries: int = 3,
    ):
        """Initialize the partial fill handler.
        
        Args:
            timeout_sec: Seconds before force-closing remaining amount
            max_retries: Maximum retry attempts for close
        """
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        
        # Active partial fills
        self._partials: Dict[str, PartialFill] = {}
        
        # Adjustment history
        self._adjustments: list[FillAdjustment] = []
        
        # Callbacks for external state updates
        self._on_adjustment: Optional[callable] = None
        self._on_exposure_update: Optional[callable] = None
    
    def set_adjustment_callback(self, callback: callable) -> None:
        """Set callback for adjustment notifications.
        
        Args:
            callback: Function to call on adjustment events
        """
        self._on_adjustment = callback
    
    def set_exposure_update_callback(self, callback: callable) -> None:
        """Set callback for exposure updates.
        
        Args:
            callback: Function to call on exposure changes
        """
        self._on_exposure_update = callback
    
    def on_partial_fill(
        self,
        signal_id: str,
        mint: str,
        expected_amount: float,
        filled_amount: float,
        entry_price: float,
        tx_sig: str,
        trace_id: Optional[str] = None,
    ) -> PartialFill:
        """Register a partial fill.
        
        Args:
            signal_id: Signal that triggered the trade
            mint: Token mint address
            expected_amount: Expected total fill amount
            filled_amount: Amount filled in this transaction
            entry_price: Average entry price
            tx_sig: Transaction signature
            trace_id: Optional trace ID for logging
            
        Returns:
            PartialFill record
        """
        if trace_id is None:
            trace_id = str(uuid.uuid4())[:8]
        
        # Check if partial fill already exists
        if signal_id in self._partials:
            existing = self._partials[signal_id]
            # Update existing partial fill
            existing.filled_amount += filled_amount
            existing.last_update = datetime.now(timezone.utc)
            
            if existing.filled_amount >= expected_amount:
                existing.status = "completed"
                logger.info(
                    f"[partial_fill] {signal_id} fully filled: "
                    f"{existing.filled_amount:.2f}/{expected_amount:.2f}"
                )
            
            return existing
        
        # Create new partial fill
        partial = PartialFill(
            signal_id=signal_id,
            mint=mint,
            expected_amount=expected_amount,
            filled_amount=filled_amount,
            entry_price=entry_price,
            tx_sig=tx_sig,
            trace_id=trace_id,
        )
        
        self._partials[signal_id] = partial
        
        # Log adjustment
        self._log_adjustment(
            FillAdjustment(
                signal_id=signal_id,
                mint=mint,
                adjustment_type="partial_fill",
                tx_sig=tx_sig,
                trace_id=trace_id,
                filled_amount=filled_amount,
                remaining_amount=expected_amount - filled_amount,
                price=entry_price,
                reason="Partial fill received",
            )
        )
        
        logger.info(
            f"[partial_fill] {signal_id}: {filled_amount:.2f}/{expected_amount:.2f} "
            f"(tx={tx_sig[:8]}..., trace={trace_id})"
        )
        
        return partial
    
    def is_expired(self, signal_id: str) -> bool:
        """Check if partial fill has exceeded timeout.
        
        Args:
            signal_id: Signal ID to check
            
        Returns:
            True if expired
        """
        partial = self._partials.get(signal_id)
        if partial is None or partial.status != "pending":
            return False
        
        elapsed = (datetime.now(timezone.utc) - partial.created_at).total_seconds()
        return elapsed > self.timeout_sec
    
    def get_remaining_amount(self, signal_id: str) -> float:
        """Get remaining amount for a partial fill.
        
        Args:
            signal_id: Signal ID to check
            
        Returns:
            Remaining amount, or 0 if not found
        """
        partial = self._partials.get(signal_id)
        if partial is None:
            return 0.0
        return max(0.0, partial.expected_amount - partial.filled_amount)
    
    def force_close_remaining(
        self,
        signal_id: str,
        close_price: float,
        reason: str = "partial_timeout",
    ) -> Optional[FillAdjustment]:
        """Force close the remaining amount for a partial fill.
        
        Args:
            signal_id: Signal ID to close
            close_price: Close price
            reason: Reason for close
            
        Returns:
            FillAdjustment if close was processed
        """
        partial = self._partials.get(signal_id)
        if partial is None or partial.status != "pending":
            return None
        
        remaining = self.get_remaining_amount(signal_id)
        if remaining <= 0:
            partial.status = "completed"
            return None
        
        # Create close tx signature placeholder
        close_tx_sig = f"close_{partial.tx_sig}"
        
        adjustment = FillAdjustment(
            signal_id=signal_id,
            mint=partial.mint,
            adjustment_type="force_close",
            tx_sig=close_tx_sig,
            trace_id=partial.trace_id,
            filled_amount=partial.filled_amount,
            remaining_amount=0.0,
            price=close_price,
            reason=reason,
        )
        
        # Update partial fill status
        partial.status = "closed"
        
        # Log adjustment
        self._log_adjustment(adjustment)
        
        # Notify external callbacks
        if self._on_adjustment:
            self._on_adjustment(adjustment)
        
        logger.info(
            f"[partial_fill] {signal_id} force closed: "
            f"filled={partial.filled_amount:.2f}, remaining={remaining:.2f} "
            f"@ {close_price} (reason={reason})"
        )
        
        return adjustment
    
    def cancel_remaining(
        self,
        signal_id: str,
        reason: str = "cancel_requested",
    ) -> Optional[FillAdjustment]:
        """Cancel the remaining amount for a partial fill.
        
        Args:
            signal_id: Signal ID to cancel
            reason: Reason for cancel
            
        Returns:
            FillAdjustment if cancel was processed
        """
        partial = self._partials.get(signal_id)
        if partial is None or partial.status != "pending":
            return None
        
        remaining = self.get_remaining_amount(signal_id)
        
        # Create cancel tx signature placeholder
        cancel_tx_sig = f"cancel_{partial.tx_sig}"
        
        adjustment = FillAdjustment(
            signal_id=signal_id,
            mint=partial.mint,
            adjustment_type="cancel",
            tx_sig=cancel_tx_sig,
            trace_id=partial.trace_id,
            filled_amount=partial.filled_amount,
            remaining_amount=remaining,
            price=partial.entry_price,
            reason=reason,
        )
        
        # Update partial fill status
        partial.status = "closed"
        
        # Log adjustment
        self._log_adjustment(adjustment)
        
        # Notify external callbacks
        if self._on_adjustment:
            self._on_adjustment(adjustment)
        
        logger.info(
            f"[partial_fill] {signal_id} cancelled: "
            f"filled={partial.filled_amount:.2f}, remaining={remaining:.2f} "
            f"(reason={reason})"
        )
        
        return adjustment
    
    def get_pending_partials(self) -> list[PartialFill]:
        """Get all pending partial fills."""
        return [
            p for p in self._partials.values()
            if p.status == "pending"
        ]
    
    def check_timeouts(self) -> list[FillAdjustment]:
        """Check all pending partials for timeout.
        
        Returns:
            List of FillAdjustment for expired fills
        """
        adjustments = []
        for partial in self.get_pending_partials():
            if self.is_expired(partial.signal_id):
                adjustment = self.force_close_remaining(
                    partial.signal_id,
                    partial.entry_price,
                    reason="partial_timeout",
                )
                if adjustment:
                    adjustments.append(adjustment)
        return adjustments
    
    def get_adjustment_history(self) -> list[Dict[str, Any]]:
        """Get all adjustments as dictionaries."""
        return [adj.to_dict() for adj in self._adjustments]
    
    def _log_adjustment(self, adjustment: FillAdjustment) -> None:
        """Log an adjustment to history."""
        self._adjustments.append(adjustment)
        
        # Notify external callbacks
        if self._on_adjustment:
            try:
                self._on_adjustment(adjustment)
            except Exception as e:
                logger.error(f"[partial_fill] Adjustment callback failed: {e}")
    
    def get_status(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """Get status for a partial fill.
        
        Args:
            signal_id: Signal ID to check
            
        Returns:
            Status dict or None
        """
        partial = self._partials.get(signal_id)
        if partial is None:
            return None
        
        remaining = self.get_remaining_amount(signal_id)
        elapsed = (datetime.now(timezone.utc) - partial.created_at).total_seconds()
        
        return {
            "signal_id": partial.signal_id,
            "mint": partial.mint,
            "expected_amount": partial.expected_amount,
            "filled_amount": partial.filled_amount,
            "remaining_amount": remaining,
            "fill_percent": (partial.filled_amount / partial.expected_amount * 100) if partial.expected_amount > 0 else 0,
            "status": partial.status,
            "elapsed_sec": elapsed,
            "expired": self.is_expired(partial.signal_id),
            "tx_sig": partial.tx_sig,
            "trace_id": partial.trace_id,
        }
