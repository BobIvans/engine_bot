"""execution/models.py

Data models for execution management and retry logic.
PR-Z.2: Order model extension for partial fill retry tracking.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

@dataclass
class Order:
    """
    Represents an execution order with retry chain tracking.
    
    Attributes:
        client_id: Unique identifier for this specific attempt.
        original_client_id: Identifier of the root order in the chain.
        retry_attempt: Attempt number (0 = initial).
        original_size: Initial requested size in tokens (or base units).
        cumulative_filled: Total amount filled across previous attempts.
        created_at: Timestamp of the first attempt creation.
        
        input_mint: Token to swap from.
        output_mint: Token to swap to.
        amount: Amount to swap in this attempt (atomic units/lamports?). 
                Note: Implementation Plan said float/Decimal. 
                LiveExecutor uses int (lamports). 
                We will use int to match LiveExecutor for amount.
                But original_size might be float (tokens)?
                Let's stick to int (lamports) for precision if possible.
                However, partial fill logic uses `Decimal` in plan: `chain.cumulative_filled += filled_amount`.
                Let's use int for amount (atomic) to avoid float issues.
                original_size: int (atomic units).
        side: "BUY" or "SELL".
        slippage_bps: Max slippage.
        priority_fee_micro_lamports: Priority fee for this attempt.
    """
    client_id: str
    original_client_id: str
    retry_attempt: int
    original_size: int  # Atomic units
    cumulative_filled: int = 0
    created_at: float = 0.0
    
    input_mint: str = ""
    output_mint: str = ""
    amount: int = 0  # Atomic units for THIS attempt
    side: str = "BUY"
    slippage_bps: int = 100
    priority_fee_micro_lamports: int = 0
    
    def __post_init__(self):
        if self.created_at == 0.0:
            import time
            self.created_at = time.time()
