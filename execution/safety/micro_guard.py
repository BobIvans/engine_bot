"""
execution/safety/micro_guard.py

Micro-Live Execution Mode Safety Guard.

Provides hard-coded safety limits for micro-trading on mainnet.

PR-U.5
"""
import sys
from dataclasses import dataclass
from typing import List, Optional

# Hard-coded safety limits (cannot be overridden)
MAX_MICRO_TRADE_SOL = 0.1  # Maximum 0.1 SOL per trade
MAX_MICRO_DAILY_LOSS_SOL = 0.5  # Maximum 0.5 SOL daily loss
MAX_MICRO_EXPOSURE_SOL = 1.0  # Maximum 1.0 SOL total exposure


class SafetyViolationError(Exception):
    """Raised when a safety check fails."""
    
    def __init__(self, reason: str, details: Optional[dict] = None):
        self.reason = reason
        self.details = details or {}
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        msg = f"SAFETY_VIOLATION: {self.reason}"
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            msg += f" [{details_str}]"
        return msg


@dataclass
class SafetyConfig:
    """Configuration for micro-live safety limits."""
    max_trade_sol: float = 0.05  # Configurable but bounded by MAX_MICRO_TRADE_SOL
    max_daily_loss_sol: float = 0.2  # Configurable but bounded by MAX_MICRO_DAILY_LOSS_SOL
    allowed_wallets: List[str] = None  # List of allowed wallet addresses
    
    def __post_init__(self):
        if self.allowed_wallets is None:
            self.allowed_wallets = []
        
        # Enforce hard limits from config
        self.max_trade_sol = min(self.max_trade_sol, MAX_MICRO_TRADE_SOL)
        self.max_daily_loss_sol = min(self.max_daily_loss_sol, MAX_MICRO_DAILY_LOSS_SOL)


class MicroSafetyGuard:
    """
    Safety guard for Micro-Live execution mode.
    
    Validates all orders against hard-coded safety limits.
    
    PR-U.5
    """
    
    # Class-level constants (hard-coded, cannot be changed)
    MAX_TRADE_SOL = MAX_MICRO_TRADE_SOL
    MAX_DAILY_LOSS_SOL = MAX_MICRO_DAILY_LOSS_SOL
    MAX_EXPOSURE_SOL = MAX_MICRO_EXPOSURE_SOL
    
    def __init__(self, config: SafetyConfig):
        """
        Initialize the safety guard.
        
        Args:
            config: SafetyConfig with allowed wallets and limits
        """
        self.config = config
        self._log_info(f"MicroSafetyGuard initialized with limits:")
        self._log_info(f"  max_trade_sol: {config.max_trade_sol}")
        self._log_info(f"  max_daily_loss_sol: {config.max_daily_loss_sol}")
        self._log_info(f"  allowed_wallets: {len(config.allowed_wallets)} wallets")
    
    def _log_info(self, msg: str):
        """Log info message to stderr."""
        print(f"[micro_guard] {msg}", file=sys.stderr)
    
    def _log_reject(self, msg: str, details: Optional[dict] = None):
        """Log rejection to stderr."""
        details_str = ""
        if details:
            details_str = " " + ", ".join(f"{k}={v}" for k, v in details.items())
        print(f"[micro_guard] REJECT: {msg}{details_str}", file=sys.stderr)
    
    def validate_order(
        self,
        wallet_source: str,
        amount_in_sol: float,
        current_exposure_sol: float,
        daily_loss_sol: float,
    ) -> bool:
        """
        Validate an order against safety limits.
        
        Args:
            wallet_source: Source wallet address
            amount_in_sol: Amount to trade in SOL
            current_exposure_sol: Current market exposure in SOL
            daily_loss_sol: Current daily loss in SOL
            
        Returns:
            True if order passes all checks
            
        Raises:
            SafetyViolationError: If any check fails
        """
        # Check 1: Amount limit
        if amount_in_sol > self.config.max_trade_sol:
            self._log_reject(
                f"Trade amount {amount_in_sol} SOL exceeds limit {self.config.max_trade_sol} SOL",
                {"amount": amount_in_sol, "limit": self.config.max_trade_sol}
            )
            raise SafetyViolationError(
                f"Trade amount {amount_in_sol} SOL exceeds limit {self.config.max_trade_sol} SOL",
                {"amount_in_sol": amount_in_sol, "limit": self.config.max_trade_sol}
            )
        
        # Check 2: Wallet allowlist
        if wallet_source not in self.config.allowed_wallets:
            self._log_reject(
                f"Wallet not in allowlist: {wallet_source[:8]}...",
                {"wallet": wallet_source[:8] + "...", "allowed_count": len(self.config.allowed_wallets)}
            )
            raise SafetyViolationError(
                f"Wallet not in allowlist: {wallet_source[:8]}...",
                {"wallet_source": wallet_source[:8] + "..."}
            )
        
        # Check 3: Daily loss limit
        if daily_loss_sol >= self.config.max_daily_loss_sol:
            self._log_reject(
                f"Daily loss {daily_loss_sol} SOL exceeds limit {self.config.max_daily_loss_sol} SOL",
                {"daily_loss": daily_loss_sol, "limit": self.config.max_daily_loss_sol}
            )
            raise SafetyViolationError(
                f"Daily loss {daily_loss_sol} SOL exceeds limit {self.config.max_daily_loss_sol} SOL",
                {"daily_loss_sol": daily_loss_sol, "limit": self.config.max_daily_loss_sol}
            )
        
        # Check 4: Exposure limit
        new_exposure = current_exposure_sol + amount_in_sol
        if new_exposure > self.MAX_EXPOSURE_SOL:
            self._log_reject(
                f"Total exposure {new_exposure} SOL exceeds limit {self.MAX_EXPOSURE_SOL} SOL",
                {"new_exposure": new_exposure, "current": current_exposure_sol, "limit": self.MAX_EXPOSURE_SOL}
            )
            raise SafetyViolationError(
                f"Total exposure {new_exposure} SOL exceeds limit {self.MAX_EXPOSURE_SOL} SOL",
                {"new_exposure": new_exposure, "current_exposure": current_exposure_sol, "limit": self.MAX_EXPOSURE_SOL}
            )
        
        self._log_info(f"Order validated: {amount_in_sol} SOL from {wallet_source[:8]}... (OK)")
        return True
    
    def is_wallet_allowed(self, wallet: str) -> bool:
        """Check if a wallet is in the allowlist."""
        return wallet in self.config.allowed_wallets
    
    def get_limits(self) -> dict:
        """Return current safety limits."""
        return {
            "max_trade_sol": self.config.max_trade_sol,
            "max_daily_loss_sol": self.config.max_daily_loss_sol,
            "max_exposure_sol": self.MAX_EXPOSURE_SOL,
            "allowed_wallets_count": len(self.config.allowed_wallets),
        }
