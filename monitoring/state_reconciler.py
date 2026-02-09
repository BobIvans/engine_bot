"""
State Reconciler (PR-X.1)

Watchdog mechanism that periodically reconciles on-chain vs local balance.
Detects discrepancies and creates adjustment records.

HARD RULES:
- Reconciliation ONLY in live mode (not paper/sim)
- Non-blocking calls to main execution loop
- In --dry-run: reconciliation happens but adjustments NOT applied
- All balance changes go through explicit Adjustment Record
- Alerts ONLY when delta > threshold
- No writes to stdout (summary-json remains unchanged)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AdjustmentReason(Enum):
    """Reasons for balance adjustment."""
    MISSED_TX = "missed_tx"
    REORG = "reorg"
    RPC_INCONSISTENCY = "rpc_inconsistency"
    MANUAL = "manual"
    UNKNOWN = "unknown"


@dataclass
class BalanceAdjustment:
    """
    Adjustment record for balance reconciliation.
    
    Attributes:
        timestamp: When the adjustment was created
        local_balance_lamports_before: Balance before adjustment
        onchain_balance_lamports: Actual on-chain balance
        delta_lamports: Difference (onchain - local)
        reason: Why the adjustment is needed
        tx_signatures: Associated transaction signatures if known
        adjusted: Whether the adjustment was applied
    """
    timestamp: datetime
    local_balance_lamports_before: int
    onchain_balance_lamports: int
    delta_lamports: int
    reason: str
    tx_signatures: List[str] = field(default_factory=list)
    adjusted: bool = False
    
    @property
    def abs_delta(self) -> int:
        """Return absolute value of delta."""
        return abs(self.delta_lamports)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "local_balance_lamports_before": self.local_balance_lamports_before,
            "onchain_balance_lamports": self.onchain_balance_lamports,
            "delta_lamports": self.delta_lamports,
            "reason": self.reason,
            "tx_signatures": self.tx_signatures,
            "adjusted": self.adjusted,
        }


@dataclass
class ReconcilerConfig:
    """
    Configuration for state reconciliation.
    
    Attributes:
        enabled: Whether reconciliation is enabled
        interval_seconds: How often to check (default: 300 = 5 min)
        warning_threshold_lamports: Alert threshold (default: 0.005 SOL)
        critical_threshold_lamports: Critical alert threshold (default: 0.05 SOL)
        max_delta_without_alert_lamports: Ignore small discrepancies
    """
    enabled: bool = True
    interval_seconds: int = 300
    warning_threshold_lamports: int = 5_000_000  # ~0.005 SOL
    critical_threshold_lamports: int = 50_000_000  # ~0.05 SOL
    max_delta_without_alert_lamports: int = 1_000_000  # ~0.001 SOL
    
    def __post_init__(self):
        if self.warning_threshold_lamports > self.critical_threshold_lamports:
            raise ValueError("warning_threshold must be <= critical_threshold")


class StateReconciler:
    """
    Reconciles on-chain balance with local portfolio state.
    
    Usage:
        reconciler = StateReconciler(
            rpc_client=connection,
            wallet_pubkey=wallet.pubkey(),
            portfolio_state=portfolio,
            config=ReconcilerConfig(),
        )
        
        adjustment = await reconciler.check_and_reconcile()
        if adjustment:
            # Alert and log
            send_alert(level="WARNING", type="balance_discrepancy", ...)
    """
    
    def __init__(
        self,
        rpc_client: Any,  # Solana connection or RPC client
        wallet_pubkey: Any,  # Pubkey object
        portfolio_state: Any,  # PortfolioState or similar
        config: ReconcilerConfig = None,
        dry_run: bool = False,
    ):
        """
        Initialize the state reconciler.
        
        Args:
            rpc_client: Solana RPC client (must have get_balance method)
            wallet_pubkey: Wallet public key
            portfolio_state: Local portfolio state with bankroll_lamports
            config: Reconciliation configuration
            dry_run: If True, don't apply adjustments
        """
        self.rpc_client = rpc_client
        self.wallet_pubkey = wallet_pubkey
        self.portfolio_state = portfolio_state
        self.config = config or ReconcilerConfig()
        self.dry_run = dry_run
        
        # Track last known balance for trend detection
        self._last_onchain_balance: Optional[int] = None
        self._adjustments: List[BalanceAdjustment] = []
    
    async def get_onchain_balance(self) -> int:
        """
        Get current on-chain balance in lamports.
        
        Returns:
            Balance in lamports.
            
        Raises:
            RPCError: If RPC call fails.
        """
        try:
            # Try different RPC client interfaces
            if hasattr(self.rpc_client, 'get_balance'):
                response = await self.rpc_client.get_balance(self.wallet_pubkey)
                return response.value if hasattr(response, 'value') else response
            elif hasattr(self.rpc_client, 'get_balance_lamports'):
                return await self.rpc_client.get_balance_lamports(self.wallet_pubkey)
            else:
                # Fallback: try calling method
                balance = await self.rpc_client.get_balance(self.wallet_pubkey)
                return balance if isinstance(balance, int) else balance.value
        except Exception as e:
            logger.error(f"[reconciler] Failed to get onchain balance: {e}")
            raise
    
    def get_local_balance(self) -> int:
        """
        Get local portfolio balance in lamports.
        
        Returns:
            Local balance in lamports.
        """
        # Try different portfolio state interfaces
        if hasattr(self.portfolio_state, 'bankroll_lamports'):
            return self.portfolio_state.bankroll_lamports
        elif hasattr(self.portfolio_state, 'bankroll'):
            bankroll = self.portfolio_state.bankroll
            return int(bankroll * 1_000_000_000) if bankroll else 0
        elif hasattr(self.portfolio_state, 'get_balance'):
            return self.portfolio_state.get_balance()
        else:
            # Default: try to access as attribute
            return getattr(self.portfolio_state, 'balance', 0)
    
    def _determine_reason(
        self,
        delta: int,
        last_balance: Optional[int],
        current_balance: int,
    ) -> str:
        """
        Determine the reason for the balance discrepancy.
        
        Args:
            delta: Difference between onchain and local
            last_balance: Previous onchain balance (if any)
            current_balance: Current onchain balance
            
        Returns:
            Reason string from AdjustmentReason enum.
        """
        if last_balance is None:
            return AdjustmentReason.UNKNOWN.value
        
        # Calculate what changed on-chain
        onchain_change = current_balance - last_balance
        local_change = delta
        
        if onchain_change != local_change:
            # Something happened on-chain that wasn't in local state
            if abs(onchain_change) > abs(local_change):
                return AdjustmentReason.MISSED_TX.value
            else:
                return AdjustmentReason.REORG.value
        
        return AdjustmentReason.RPC_INCONSISTENCY.value
    
    async def check_and_reconcile(self) -> Optional[BalanceAdjustment]:
        """
        Check balance and reconcile if needed.
        
        Steps:
        1. Get onchain balance
        2. Compare with local portfolio state
        3. If |delta| > threshold:
           - Create Adjustment Record
           - Apply adjustment (unless dry_run)
           - Trigger alert
           - Log the discrepancy
        
        Returns:
            BalanceAdjustment if created, None if no action needed.
        """
        try:
            # Get both balances
            onchain_balance = await self.get_onchain_balance()
            local_balance = self.get_local_balance()
            
            delta = onchain_balance - local_balance
            
            # Check if delta exceeds threshold
            threshold = self.config.max_delta_without_alert_lamports
            
            if abs(delta) <= threshold:
                logger.debug(
                    f"[reconciler] Balance within threshold: "
                    f"onchain={onchain_balance}, local={local_balance}, delta={delta}"
                )
                return None
            
            # Determine reason for discrepancy
            reason = self._determine_reason(delta, self._last_onchain_balance, onchain_balance)
            
            # Create adjustment record
            adjustment = BalanceAdjustment(
                timestamp=datetime.utcnow(),
                local_balance_lamports_before=local_balance,
                onchain_balance_lamports=onchain_balance,
                delta_lamports=delta,
                reason=reason,
                adjusted=False,
            )
            
            logger.warning(
                f"[reconciler] Balance discrepancy detected: "
                f"delta={delta}, reason={reason}"
            )
            
            # Apply adjustment unless dry_run
            if not self.dry_run:
                self._apply_adjustment(adjustment)
                adjustment.adjusted = True
                logger.info(f"[reconciler] Adjustment applied: {adjustment.to_dict()}")
            else:
                logger.info(f"[reconciler] Dry run - adjustment NOT applied: {adjustment.to_dict()}")
            
            # Track for future comparisons
            self._last_onchain_balance = onchain_balance
            self._adjustments.append(adjustment)
            
            return adjustment
            
        except Exception as e:
            logger.error(f"[reconciler] Error during reconciliation: {e}")
            raise
    
    def _apply_adjustment(self, adjustment: BalanceAdjustment) -> None:
        """
        Apply adjustment to local portfolio state.
        
        Args:
            adjustment: The adjustment to apply.
        """
        # Update local balance to match onchain
        if hasattr(self.portfolio_state, 'bankroll_lamports'):
            self.portfolio_state.bankroll_lamports = adjustment.onchain_balance_lamports
        elif hasattr(self.portfolio_state, 'bankroll'):
            new_bankroll = adjustment.onchain_balance_lamports / 1_000_000_000
            self.portfolio_state.bankroll = new_bankroll
        elif hasattr(self.portfolio_state, 'set_balance'):
            self.portfolio_state.set_balance(adjustment.onchain_balance_lamports)
        else:
            # Fallback: set as attribute
            setattr(self.portfolio_state, 'balance', adjustment.onchain_balance_lamports)
    
    def get_alert_level(self, adjustment: BalanceAdjustment) -> str:
        """
        Determine alert level based on delta magnitude.
        
        Args:
            adjustment: The balance adjustment.
            
        Returns:
            Alert level: "INFO", "WARNING", or "CRITICAL".
        """
        delta = adjustment.abs_delta
        
        if delta >= self.config.critical_threshold_lamports:
            return "CRITICAL"
        elif delta >= self.config.warning_threshold_lamports:
            return "WARNING"
        else:
            return "INFO"
    
    def get_recent_adjustments(self, limit: int = 10) -> List[BalanceAdjustment]:
        """
        Get recent adjustment records.
        
        Args:
            limit: Maximum number of adjustments to return.
            
        Returns:
            List of recent adjustments.
        """
        return self._adjustments[-limit:]
    
    def export_adjustments(self) -> List[Dict[str, Any]]:
        """
        Export all adjustments as dictionaries.
        
        Returns:
            List of adjustment dictionaries.
        """
        return [adj.to_dict() for adj in self._adjustments]
