"""
Order State Machine (PR-E.5)

Position lifecycle management with TTL and bracket orders.

HARD RULES:
- TTL counts from fill moment (not signal)
- All state transitions logged with timestamp and reason
- Force close (TTL/TP/SL) must be idempotent
- stdout unchanged (--summary-json)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from enum import Enum

import json


class PositionStatus(Enum):
    """Position lifecycle states."""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"


class CloseReason(Enum):
    """Reasons for position closure."""
    TTL_EXPIRED = "ttl_expired"
    TP_HIT = "tp_hit"
    SL_HIT = "sl_hit"
    MANUAL_CLOSE = "manual_close"
    REORG = "reorg"
    ERROR = "error"


@dataclass
class PositionState:
    """
    Complete position state for lifecycle management.
    
    Attributes:
        signal_id: Unique signal identifier
        mint: Token mint address
        entry_price: Filled price
        size_usd: Position size in USD
        entry_ts: Fill timestamp
        ttl_expires_at: TTL expiration timestamp
        tp_price: Take-profit price (optional)
        sl_price: Stop-loss price (optional)
        status: Current position status
        close_reason: Reason for closure (if closed)
        close_price: Exit price (if closed)
        close_ts: Closure timestamp (if closed)
        remaining_size_usd: Remaining position size (for partials)
    """
    signal_id: str
    mint: str
    entry_price: float
    size_usd: float
    entry_ts: datetime
    ttl_expires_at: datetime
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    status: PositionStatus = PositionStatus.PENDING
    close_reason: Optional[str] = None
    close_price: Optional[float] = None
    close_ts: Optional[datetime] = None
    remaining_size_usd: float = 0.0
    
    def __post_init__(self):
        if self.remaining_size_usd == 0.0:
            self.remaining_size_usd = self.size_usd
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "signal_id": self.signal_id,
            "mint": self.mint,
            "entry_price": self.entry_price,
            "size_usd": self.size_usd,
            "entry_ts": self.entry_ts.isoformat(),
            "ttl_expires_at": self.ttl_expires_at.isoformat(),
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "status": self.status.value,
            "close_reason": self.close_reason,
            "close_price": self.close_price,
            "close_ts": self.close_ts.isoformat() if self.close_ts else None,
            "remaining_size_usd": self.remaining_size_usd,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionState":
        """Deserialize from dictionary."""
        data = data.copy()
        data["entry_ts"] = datetime.fromisoformat(data["entry_ts"])
        data["ttl_expires_at"] = datetime.fromisoformat(data["ttl_expires_at"])
        if data.get("close_ts"):
            data["close_ts"] = datetime.fromisoformat(data["close_ts"])
        data["status"] = PositionStatus(data["status"])
        return cls(**data)
    
    @property
    def is_active(self) -> bool:
        """Check if position is still active."""
        return self.status in (PositionStatus.ACTIVE, PositionStatus.PENDING)
    
    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.status in (PositionStatus.CLOSED, PositionStatus.EXPIRED)
    
    def check_ttl(self, current_ts: datetime) -> bool:
        """Check if TTL has expired."""
        return current_ts >= self.ttl_expires_at
    
    def check_tp(self, current_price: float, side: str = "BUY") -> bool:
        """Check if take-profit is hit."""
        if self.tp_price is None:
            return False
        if side == "BUY":
            return current_price >= self.tp_price
        else:  # SELL
            return current_price <= self.tp_price
    
    def check_sl(self, current_price: float, side: str = "BUY") -> bool:
        """Check if stop-loss is hit."""
        if self.sl_price is None:
            return False
        if side == "BUY":
            return current_price <= self.sl_price
        else:  # SELL
            return current_price >= self.sl_price


@dataclass
class CloseAction:
    """
    Action to be performed on a position.
    
    Attributes:
        signal_id: Position to act on
        action_type: Type of action (CLOSE, PARTIAL_CLOSE)
        reason: Reason for action
        price: Target close price (optional)
        size_usd: Size to close (optional, defaults to full position)
    """
    signal_id: str
    action_type: Literal["CLOSE", "PARTIAL_CLOSE"]
    reason: str
    price: Optional[float] = None
    size_usd: Optional[float] = None
    
    def __post_init__(self):
        if self.size_usd is None:
            self.size_usd = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "signal_id": self.signal_id,
            "action_type": self.action_type,
            "reason": self.reason,
            "price": self.price,
            "size_usd": self.size_usd,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CloseAction":
        """Deserialize from dictionary."""
        return cls(**data)


@dataclass
class OrderManagerConfig:
    """
    Configuration for order management.
    
    Attributes:
        check_interval_seconds: How often to check positions
        default_ttl_seconds: Default TTL if not specified
        enable_partial_closes: Allow partial position closes
        max_positions: Maximum concurrent positions
    """
    check_interval_seconds: int = 5
    default_ttl_seconds: int = 3600  # 1 hour
    enable_partial_closes: bool = False
    max_positions: int = 10
    
    def __post_init__(self):
        if self.check_interval_seconds < 1:
            raise ValueError("check_interval must be >= 1")
        if self.max_positions < 1:
            raise ValueError("max_positions must be >= 1")


# Transition logging helper
def log_transition(
    position: PositionState,
    old_status: PositionStatus,
    new_status: PositionStatus,
    reason: str,
) -> None:
    """Log position state transition."""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(
        f"[order_sm] Transition: {position.signal_id} "
        f"{old_status.value} -> {new_status.value} "
        f"(reason: {reason})"
    )
