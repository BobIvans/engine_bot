"""
State Reconciler Worker (PR-X.1)

Background daemon that runs the reconciliation loop.
Handles graceful shutdown and error recovery.

HARD RULES:
- Runs ONLY in live mode
- Non-blocking to main execution
- Graceful shutdown on signals
- Exponential backoff on RPC errors
"""

import asyncio
import logging
import signal
from datetime import datetime
from typing import Any, Optional

from monitoring.state_reconciler import (
    StateReconciler,
    ReconcilerConfig,
    BalanceAdjustment,
)
from monitoring.alerts import send_alert

logger = logging.getLogger(__name__)


class StateReconcilerWorker:
    """
    Background worker for state reconciliation.
    
    Runs an async loop that periodically checks balance alignment.
    
    Usage:
        worker = StateReconcilerWorker(
            rpc_client=connection,
            wallet_pubkey=wallet.pubkey(),
            portfolio_state=portfolio,
            config=ReconcilerConfig(),
        )
        
        await worker.run()  # Runs until shutdown
    """
    
    def __init__(
        self,
        rpc_client: Any,
        wallet_pubkey: Any,
        portfolio_state: Any,
        config: ReconcilerConfig = None,
        dry_run: bool = False,
        alert_callback: Optional[Any] = None,
    ):
        """
        Initialize the reconciler worker.
        
        Args:
            rpc_client: Solana RPC client
            wallet_pubkey: Wallet public key
            portfolio_state: Local portfolio state
            config: Reconciliation configuration
            dry_run: If True, don't apply adjustments
            alert_callback: Optional custom alert handler
        """
        self.reconciler = StateReconciler(
            rpc_client=rpc_client,
            wallet_pubkey=wallet_pubkey,
            portfolio_state=portfolio_state,
            config=config,
            dry_run=dry_run,
        )
        self.alert_callback = alert_callback
        self.dry_run = dry_run
        
        # Control flags
        self._running = False
        self._shutdown_requested = False
        
        # Error tracking for backoff
        self._consecutive_errors = 0
        self._base_delay = config.interval_seconds if config else 300
    
    async def _run_loop(self) -> None:
        """Main reconciliation loop."""
        self._running = True
        
        logger.info("[reconciler_worker] Starting reconciliation loop...")
        
        while self._running and not self._shutdown_requested:
            try:
                # Perform reconciliation
                adjustment = await self.reconciler.check_and_reconcile()
                
                if adjustment:
                    # Send alert
                    await self._handle_adjustment(adjustment)
                
                # Reset error counter on success
                self._consecutive_errors = 0
                
                # Wait until next check
                await self._sleep_with_shutdown()
                
            except asyncio.CancelledError:
                logger.info("[reconciler_worker] Reconciliation loop cancelled")
                break
            except Exception as e:
                logger.error(f"[reconciler_worker] Error in reconciliation loop: {e}")
                self._consecutive_errors += 1
                
                # Exponential backoff
                delay = min(
                    self._base_delay * (2 ** min(self._consecutive_errors, 5)),
                    3600,  # Max 1 hour
                )
                
                logger.warning(
                    f"[reconciler_worker] Backing off {delay}s after {self._consecutive_errors} errors"
                )
                
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break
        
        self._running = False
        logger.info("[reconciler_worker] Reconciliation loop stopped")
    
    async def _sleep_with_shutdown(self) -> None:
        """Sleep with early exit on shutdown."""
        delay = self._base_delay
        
        while delay > 0 and not self._shutdown_requested:
            await asyncio.sleep(min(delay, 10))
            delay -= 10
    
    async def _handle_adjustment(self, adjustment: BalanceAdjustment) -> None:
        """
        Handle a detected adjustment.
        
        - Send alert
        - Log details
        - Call custom callback if provided
        """
        # Determine alert level
        alert_level = self.reconciler.get_alert_level(adjustment)
        
        # Build alert message
        delta_sol = adjustment.delta_lamports / 1_000_000_000
        
        message = (
            f"Balance discrepancy detected!\n"
            f"On-chain: {adjustment.onchain_balance_lamports:,} lamports\n"
            f"Local: {adjustment.local_balance_lamports_before:,} lamports\n"
            f"Delta: {adjustment.delta_lamports:,} lamports ({delta_sol:+.6f} SOL)\n"
            f"Reason: {adjustment.reason}\n"
            f"Adjusted: {'Yes' if adjustment.adjusted else 'No (dry run)'}"
        )
        
        # Log the adjustment
        logger.warning(f"[reconciler_worker] {message}")
        
        # Send alert
        if self.alert_callback:
            await self.alert_callback(
                level=alert_level,
                type="balance_discrepancy",
                message=message,
                adjustment=adjustment.to_dict(),
            )
        else:
            await send_alert(
                level=alert_level,
                type="balance_discrepancy",
                message=message,
            )
    
    async def start(self) -> None:
        """Start the worker."""
        # Register signal handlers
        loop = asyncio.get_event_loop()
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._on_shutdown)
        
        await self._run_loop()
    
    def _on_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("[reconciler_worker] Shutdown signal received")
        self._shutdown_requested = True
    
    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("[reconciler_worker] Stopping worker...")
        self._running = False
        self._shutdown_requested = True
    
    @property
    def is_running(self) -> bool:
        """Check if worker is running."""
        return self._running


async def run_reconciler(
    rpc_client: Any,
    wallet_pubkey: Any,
    portfolio_state: Any,
    config: ReconcilerConfig = None,
    dry_run: bool = False,
) -> None:
    """
    Convenience function to run the reconciler until interrupted.
    
    Args:
        rpc_client: Solana RPC client
        wallet_pubkey: Wallet public key
        portfolio_state: Local portfolio state
        config: Reconciliation configuration
        dry_run: If True, don't apply adjustments
    """
    worker = StateReconcilerWorker(
        rpc_client=rpc_client,
        wallet_pubkey=wallet_pubkey,
        portfolio_state=portfolio_state,
        config=config,
        dry_run=dry_run,
    )
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("[reconciler] Interrupted by user")
    finally:
        await worker.stop()
    
    # Export final adjustments
    if worker.reconciler._adjustments:
        logger.info(
            f"[reconciler] Final adjustments: {len(worker.reconciler._adjustments)} records"
        )


# Mock classes for testing compatibility
class MockRPCClient:
    """Mock RPC client for testing."""
    
    def __init__(self, balance: int = 1_000_000_000):
        self._balance = balance
    
    async def get_balance(self, pubkey) -> Any:
        class Response:
            def __init__(self, value):
                self.value = value
        return Response(self._balance)


class MockPortfolioState:
    """Mock portfolio state for testing."""
    
    def __init__(self, bankroll_lamports: int = 1_000_000_000):
        self.bankroll_lamports = bankroll_lamports
        self.bankroll = bankroll_lamports / 1_000_000_000
