"""execution/live_executor.py

PR-G.1 Transaction Builder Adapter & Simulation.

Interface for live transaction execution on Solana:
- LiveExecutor: Abstract base class for transaction builders
- Methods for building swaps and simulating transactions

Design goals:
- No private keys: Only builds unsigned transactions and simulates
- Protocol-based: Allows for different implementations (Jupiter, Raydium, etc.)
- Fail-safe: All methods return structured error dicts on failure
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


from execution.models import Order
from execution.partial_retry import PartialFillRetryManager
from config.runtime_schema import RuntimeConfig

class LiveExecutor(ABC):
    """Abstract base class for live transaction execution.

    Implementations should:
    - build_swap_tx: Create unsigned swap transaction
    - simulate_tx: Simulate transaction before signing

    This interface does NOT handle private keys or signing.
    
    Includes Partial Fill Retry Logic (PR-Z.2).
    """
    
    def __init__(self, config: Optional[RuntimeConfig] = None):
        self.config = config
        self._retry_manager = PartialFillRetryManager(config) if (config and config.partial_retry_enabled) else None

    def on_partial_fill(self, order: Order, filled_amount: int) -> Optional[Order]:
        """Handle partial fill event, potentially generating a retry order."""
        if self._retry_manager:
            return self._retry_manager.on_partial_fill(order, filled_amount)
        return None

    def on_full_fill(self, order: Order) -> None:
        """Handle full fill event, cleaning up retry state."""
        if self._retry_manager:
            self._retry_manager.on_full_fill(order.original_client_id)
            
    # Abstract methods follow...

    @abstractmethod
    def build_swap_tx(
        self,
        *,
        wallet: str,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 100,
    ) -> Dict[str, Any]:
        """Build an unsigned swap transaction.

        Args:
            wallet: Source wallet address.
            input_mint: Input token mint address.
            output_mint: Output token mint address.
            amount_lamports: Amount to swap in lamports.
            slippage_bps: Max slippage in basis points (default: 100 = 1%).

        Returns:
            Dict with:
            - success: bool
            - tx_base64: str (unsigned transaction in base64)
            - error: str (if success=False)
            - details: dict (additional info like fee, routes)
        """
        ...

    @abstractmethod
    def simulate_tx(
        self,
        *,
        tx_base64: str,
        accounts: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Simulate a transaction using RPC.

        Args:
            tx_base64: Base64-encoded unsigned transaction.
            accounts: Optional list of account addresses to load.

        Returns:
            Dict with:
            - success: bool
            - logs: list[str] (simulation logs)
            - units_consumed: int (CU units)
            - error: str (if success=False)
            - details: dict (additional simulation data)
        """
        ...

    @abstractmethod
    def get_quote(
        self,
        *,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 100,
    ) -> Dict[str, Any]:
        """Get a swap quote without building a transaction.

        Args:
            input_mint: Input token mint address.
            output_mint: Output token mint address.
            amount_lamports: Amount to swap in lamports.
            slippage_bps: Max slippage in basis points.

        Returns:
            Dict with:
            - success: bool
            - out_amount: int (estimated output)
            - price_impact_pct: float
            - error: str (if success=False)
        """
        ...


class NoOpLiveExecutor(LiveExecutor):
    """No-op executor for testing when live execution is disabled."""

    def build_swap_tx(
        self,
        *,
        wallet: str,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 100,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "tx_base64": "",
            "error": "LiveExecutor not enabled",
            "details": {},
        }

    def simulate_tx(
        self,
        *,
        tx_base64: str,
        accounts: Optional[list] = None,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "logs": [],
            "units_consumed": 0,
            "error": "LiveExecutor not enabled",
            "details": {},
        }

    def get_quote(
        self,
        *,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 100,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "out_amount": 0,
            "price_impact_pct": 0.0,
            "error": "LiveExecutor not enabled",
        }
