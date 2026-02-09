"""execution/position_state.py

Position state management for TTL, TP, and SL tracking.

This module defines the Position state machine and related data structures
for managing the lifecycle of positions after entry.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional, Dict, Any


# Position status literals
POSITION_ACTIVE = "ACTIVE"
POSITION_PARTIAL = "PARTIAL"
POSITION_CLOSED = "CLOSED"
POSITION_EXPIRED = "EXPIRED"


@dataclass
class Position:
    """Represents an active position with TTL, TP, and SL parameters.
    
    TTL is measured from the moment of fill (entry_ts), not from signal creation.
    """
    signal_id: str
    mint: str
    entry_price: float
    size_usd: float
    filled_usd: float
    entry_ts: datetime
    ttl_expires_at: datetime
    tp_price: float  # entry * (1 + tp_pct)
    sl_price: float  # entry * (1 - sl_pct)
    status: Literal["ACTIVE", "PARTIAL", "CLOSED", "EXPIRED"] = POSITION_ACTIVE
    close_reason: Optional[str] = None
    close_price: Optional[float] = None
    close_ts: Optional[datetime] = None
    mode: str = "U"  # Strategy mode (U, U_aggr, etc.)
    wallet: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize position to dict for logging/storage."""
        return {
            "signal_id": self.signal_id,
            "mint": self.mint,
            "entry_price": self.entry_price,
            "size_usd": self.size_usd,
            "filled_usd": self.filled_usd,
            "entry_ts": self.entry_ts.isoformat(),
            "ttl_expires_at": self.ttl_expires_at.isoformat(),
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "status": self.status,
            "close_reason": self.close_reason,
            "close_price": self.close_price,
            "close_ts": self.close_ts.isoformat() if self.close_ts else None,
            "mode": self.mode,
            "wallet": self.wallet,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        """Deserialize position from dict."""
        return cls(
            signal_id=data["signal_id"],
            mint=data["mint"],
            entry_price=data["entry_price"],
            size_usd=data["size_usd"],
            filled_usd=data["filled_usd"],
            entry_ts=datetime.fromisoformat(data["entry_ts"]),
            ttl_expires_at=datetime.fromisoformat(data["ttl_expires_at"]),
            tp_price=data["tp_price"],
            sl_price=data["sl_price"],
            status=data.get("status", POSITION_ACTIVE),
            close_reason=data.get("close_reason"),
            close_price=data.get("close_price"),
            close_ts=datetime.fromisoformat(data["close_ts"]) if data.get("close_ts") else None,
            mode=data.get("mode", "U"),
            wallet=data.get("wallet", ""),
        )
    
    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Check if position TTL has expired."""
        if now is None:
            now = datetime.now(timezone.utc)
        return now >= self.ttl_expires_at
    
    def is_tp_hit(self, current_price: float, side: str = "BUY") -> bool:
        """Check if take-profit price is hit.
        
        For BUY: TP hit when current_price >= tp_price
        For SELL: TP hit when current_price <= tp_price
        """
        if side.upper() == "BUY":
            return current_price >= self.tp_price
        else:
            return current_price <= self.tp_price
    
    def is_sl_hit(self, current_price: float, side: str = "BUY") -> bool:
        """Check if stop-loss price is hit.
        
        For BUY: SL hit when current_price <= sl_price
        For SELL: SL hit when current_price >= sl_price
        """
        if side.upper() == "BUY":
            return current_price <= self.sl_price
        else:
            return current_price >= self.sl_price
    
    def remaining_ttl_sec(self, now: Optional[datetime] = None) -> float:
        """Get remaining TTL in seconds."""
        if now is None:
            now = datetime.now(timezone.utc)
        remaining = (self.ttl_expires_at - now).total_seconds()
        return max(0.0, remaining)


@dataclass
class CloseAction:
    """Represents an action to close or partially close a position."""
    signal_id: str
    size_usd: float
    order_type: Literal["MARKET_CLOSE", "PARTIAL_CLOSE"]
    reason: str
    price: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "size_usd": self.size_usd,
            "order_type": self.order_type,
            "reason": self.reason,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
        }


def create_position_from_signal(
    signal_id: str,
    mint: str,
    entry_price: float,
    size_usd: float,
    ttl_sec: int,
    tp_pct: float,
    sl_pct: float,
    mode: str = "U",
    wallet: str = "",
    entry_ts: Optional[datetime] = None,
) -> Position:
    """Create a Position from signal parameters.
    
    TTL starts from entry_ts (fill time), not signal creation.
    """
    if entry_ts is None:
        entry_ts = datetime.now(timezone.utc)
    
    ttl_expires_at = datetime.fromtimestamp(
        entry_ts.timestamp() + ttl_sec,
        tz=timezone.utc
    )
    
    # Calculate TP/SL prices
    # For BUY: TP = entry * (1 + tp_pct), SL = entry * (1 - sl_pct)
    # For SELL: TP = entry * (1 - tp_pct), SL = entry * (1 + sl_pct)
    tp_price = entry_price * (1 + tp_pct)
    sl_price = entry_price * (1 - sl_pct)
    
    return Position(
        signal_id=signal_id,
        mint=mint,
        entry_price=entry_price,
        size_usd=size_usd,
        filled_usd=size_usd,  # Assume fully filled for now
        entry_ts=entry_ts,
        ttl_expires_at=ttl_expires_at,
        tp_price=tp_price,
        sl_price=sl_price,
        mode=mode,
        wallet=wallet,
    )
