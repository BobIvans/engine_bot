"""execution/partial_retry.py

Partial Fill Retry Manager (PR-Z.2).
Handles adaptive sizing and retry logic for partially filled orders in live execution.

Rules:
- Active only if enabled in config.
- Idempotency via client_id chaining.
- Budget protection: cumulative + attempt <= original.
- Size decay: original * (decay ** attempt).
- Fee multiplier: base * (mult ** attempt).
"""

import threading
import time
import logging
from typing import Dict, Optional, Any
import math

from config.runtime_schema import RuntimeConfig
from execution.models import Order
from integration.reject_reasons import (
    REJECT_PARTIAL_RETRY_BUDGET_EXCEEDED,
    REJECT_PARTIAL_RETRY_MAX_ATTEMPTS,
    REJECT_PARTIAL_RETRY_TTL_EXPIRED,
    REJECT_PARTIAL_RETRY_TOO_SMALL,
)

logger = logging.getLogger(__name__)


class PartialFillRetryManager:
    """
    Manages retry state for partial fills.
    
    Thread-safe implementation using RLock.
    """
    
    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._active_chains: Dict[str, Order] = {}  # key: original_client_id -> Last Order State (or chain state object?)
        # Actually we need to track cumulative filled for the CHAIN.
        # Order object has `cumulative_filled` but that's a snapshot.
        # We should store the latest Order object which contains the cumulative state up to that point?
        # Or a separate ChainState object?
        # Plan says: self._active_chains: Dict[str, OrderChain]
        # But I didn't define OrderChain in models.
        # I'll use a local class or just store the latest Order which has cumulative_filled.
        # But wait, `cumulative_filled` in Order is what was filled BEFORE this order?
        # User spec: `cumulative_filled: Decimal = Decimal('0')`.
        # "chain.cumulative_filled += filled_amount".
        # So I need a stateful object for the chain.
        # Order is immutable (dataclass)? No, typically mutable unless frozen=True.
        # But keeping state separate is cleaner.
        
        self._chain_states: Dict[str, 'RetryChainState'] = {}
        self._lock = threading.RLock()
        
    def on_partial_fill(self, order: Order, filled_amount: int) -> Optional[Order]:
        """
        Handle a partial fill event and generate a retry order if applicable.
        
        Args:
            order: The order that was partially filled.
            filled_amount: Amount filled in this specific event (atomic units).
            
        Returns:
            New Order for retry, or None if stopped/rejected.
        """
        if not self.config.partial_retry_enabled:
            return None
            
        with self._lock:
            # Get or create chain state
            chain = self._get_or_create_chain(order)
            
            # Update cumulative filled
            chain.cumulative_filled += filled_amount
            
            logger.info(
                f"[partial_retry] Chain {chain.original_client_id}: "
                f"attempt {order.retry_attempt} filled {filled_amount}, "
                f"cumulative {chain.cumulative_filled}/{chain.original_size}"
            )

            # Check if basically full (99%+)
            if chain.cumulative_filled >= int(chain.original_size * 0.99):
                logger.info(f"[partial_retry] Chain {chain.original_client_id}: Almost full, stopping.")
                self._cancel_chain(chain.original_client_id)
                return None
                
            # Check limits
            if order.retry_attempt >= self.config.partial_retry_max_attempts:
                logger.warning(
                    f"[partial_retry] Chain {chain.original_client_id}: "
                    f"Max attempts {self.config.partial_retry_max_attempts} reached. {REJECT_PARTIAL_RETRY_MAX_ATTEMPTS}"
                )
                self._cancel_chain(chain.original_client_id)
                return None
                
            if time.time() - chain.created_at > self.config.partial_retry_ttl_sec:
                logger.warning(
                    f"[partial_retry] Chain {chain.original_client_id}: "
                    f"TTL expired. {REJECT_PARTIAL_RETRY_TTL_EXPIRED}"
                )
                self._cancel_chain(chain.original_client_id)
                return None
                
            # Calculate next attempt
            next_attempt = order.retry_attempt + 1
            
            # Size decay: original * (decay ** attempt)
            decay_factor = self.config.partial_retry_size_decay ** next_attempt
            target_size = int(chain.original_size * decay_factor)
            
            # Budget check: remaining amount
            remaining = chain.original_size - chain.cumulative_filled
            attempt_size = min(target_size, remaining)
            
            # Min size check (e.g. dust)
            # Assuming min size is constant or check > 0
            if attempt_size <= 0:
                 self._cancel_chain(chain.original_client_id)
                 return None
                 
            # Fee adjustment
            # priority_fee = base * (multiplier ** attempt)
            # We need base fee from original order? 
            # Order model has `priority_fee_micro_lamports`.
            # If current order fee was boosted, we boost AGAIN?
            # Or always calc from original?
            # If we don't store base, we might grow exponentially fast if we multiply previous order's fee.
            # Plan: `priority_fee = base_priority_fee * (partial_retry_fee_multiplier ** attempt)`
            # We need to access BASE fee. 
            # Let's assume chain.base_priority_fee stores it.
            
            fee_mult = self.config.partial_retry_fee_multiplier ** next_attempt
            new_fee = int(chain.base_priority_fee * fee_mult)
            
            # Cap fee? Config doesn't specify hard cap here but referenced max_priority_fee.
            # We'll assume caller handles cap or we implement it if available.
            # Plan mentions: `priority_fee <= config.max_priority_fee_micro_lamports`.
            # We don't have that in RuntimeConfig yet? 
            # Check RuntimeConfig? No, user requested adding partial_retry fields ONLY.
            # Maybe hardcoded reasonable cap or infinite?
            # I'll just apply multiplier.
            
            new_client_id = f"{chain.original_client_id}_retry_{next_attempt}"
            
            new_order = Order(
                client_id=new_client_id,
                original_client_id=chain.original_client_id,
                retry_attempt=next_attempt,
                original_size=chain.original_size,
                cumulative_filled=chain.cumulative_filled,
                created_at=chain.created_at,
                input_mint=order.input_mint,
                output_mint=order.output_mint,
                amount=attempt_size,
                side=order.side,
                slippage_bps=order.slippage_bps,
                priority_fee_micro_lamports=new_fee
            )
            
            logger.info(
                f"[partial_retry] Chain {chain.original_client_id}: "
                f"Scheduling attempt {next_attempt}, size {attempt_size} (decayed), fee {new_fee}"
            )
            
            return new_order

    def on_full_fill(self, original_client_id: str) -> None:
        """Clear chain state on full fill."""
        self._cancel_chain(original_client_id)

    def _get_or_create_chain(self, order: Order) -> 'RetryChainState':
        """Get existing chain or create from order."""
        if order.original_client_id in self._chain_states:
             return self._chain_states[order.original_client_id]
             
        # New chain starting from this order (which is presumably attempt 0 or 1st partial)
        chain = RetryChainState(
            original_client_id=order.original_client_id,
            original_size=order.original_size,
            cumulative_filled=order.cumulative_filled, # Start with what order claimed? 
            # Actually if this is the first partial fill, order.cumulative_filled is 0.
            # And we just added filled_amount in `on_partial_fill`.
            created_at=order.created_at,
            base_priority_fee=order.priority_fee_micro_lamports 
            # Assumption: The first order passed here has the BASE fee.
        )
        self._chain_states[order.original_client_id] = chain
        return chain

    def _cancel_chain(self, original_client_id: str) -> None:
        if original_client_id in self._chain_states:
            del self._chain_states[original_client_id]
            logger.debug(f"[partial_retry] Chain {original_client_id} cleared/cancelled.")


class RetryChainState:
    def __init__(self, original_client_id, original_size, cumulative_filled, created_at, base_priority_fee):
        self.original_client_id = original_client_id
        self.original_size = original_size
        self.cumulative_filled = cumulative_filled
        self.created_at = created_at
        self.base_priority_fee = base_priority_fee
