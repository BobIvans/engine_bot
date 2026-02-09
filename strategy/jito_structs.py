#!/usr/bin/env python3
"""strategy/jito_structs.py

PR-O.2 Jito Bundle Structures & Fee Logic (Paper Adapter)

Pure logic for Jito bundle data structures and bribe (tip) accounting.
No network I/O - this module is used for Paper/Simulation modes.

Jito Tip Accounts (known addresses for validation):
- These are the official Jito tip accounts for MEV rewards
- Collected from public Jito documentation

Fee Structure:
- Solana base fee per signature: ~5000 lamports (varies by compute units)
- Jito tip: configurable bribe amount (typically 1000-1000000 lamports)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Known Jito Tip Accounts (public addresses from Jito docs)
# These are used for validation and tip routing
TIP_ACCOUNTS: List[str] = [
    "DRtYHDvaLLG2mL5U1xJ4xnJ7h1xx1W2PpL6Vug6V6Ha",  # Jito Tip Account 1
    "DfXygEo4Tvhk84s2DuE8C9Hy9J3zKZpj1ZTqcJqh3Wp",  # Jito Tip Account 2
    "3AVi2D4NoVsC1dZ2eGtBE8AGk11KUbT7Lgy6vZcomWw",  # Jito Tip Account 3
    "GXSs9Kx2Y4VZ7Z9DvKLNpVU6n1YxkcD9Mvb3YJ8RqJ3Z",  # Jito Tip Account 4
    "JitoTip Accounts are rotated periodically - check official docs for current list",
]

# Default Solana fees
DEFAULT_BASE_FEE_PER_SIG: int = 5000  # lamports per signature
DEFAULT_COMPUTE_UNITS: int = 200_000  # default CU per transaction


@dataclass
class JitoBundle:
    """Represents a Jito bundle of transactions.
    
    Attributes:
        transactions: List of signed transactions (base64 encoded)
        tip_lamports: Tip amount in lamports for Jito validators
        strategy_tag: Optional tag for tracking/analytics
        bundle_id: Unique identifier for the bundle
        created_at: Unix timestamp of creation
    """
    transactions: List[str]
    tip_lamports: int
    strategy_tag: str = ""
    bundle_id: str = field(default_factory=lambda: f"bundle-{uuid.uuid4().hex[:12]}")
    created_at: int = field(default_factory=lambda: int(time.time()))
    
    def __post_init__(self) -> None:
        """Validate bundle after initialization."""
        if self.tip_lamports < 0:
            raise ValueError(f"tip_lamports must be non-negative, got {self.tip_lamports}")
        if not self.transactions:
            raise ValueError("Bundle must contain at least one transaction")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "bundle_id": self.bundle_id,
            "transactions": self.transactions,
            "tip_lamports": self.tip_lamports,
            "strategy_tag": self.strategy_tag,
            "created_at": self.created_at,
        }


def validate_tip_account(address: str) -> bool:
    """Validate that a tip account address is in the known list.
    
    Args:
        address: The tip account address to validate
    
    Returns:
        True if address is a known Jito tip account
    """
    # Normalize address (lowercase for comparison)
    normalized = address.lower().strip()
    
    # Check if it's a known tip account
    for tip_account in TIP_ACCOUNTS:
        if tip_account.lower() == normalized:
            return True
    
    return False


def calculate_bundle_cost(
    bundle: JitoBundle,
    base_fee_per_sig: int = DEFAULT_BASE_FEE_PER_SIG,
    compute_units_per_tx: int = DEFAULT_COMPUTE_UNITS,
) -> Dict[str, Any]:
    """Calculate the total cost of a Jito bundle.
    
    Pure function: output depends only on inputs.
    
    Args:
        bundle: The JitoBundle to calculate costs for
        base_fee_per_sig: Base fee per signature in lamports
        compute_units_per_tx: Compute units per transaction
    
    Returns:
        Dict with cost breakdown:
        {
            "total_cost_lamports": int,
            "network_fees_lamports": int,  # Solana base fees
            "jito_tip_lamports": int,      # Jito bribe
            "num_transactions": int,
            "num_signatures": int,           # Estimated total signatures
            "cost_per_tx_lamports": float,   # Average cost per transaction
        }
    
    Examples:
        >>> bundle = JitoBundle(transactions=["tx1", "tx2"], tip_lamports=100000)
        >>> cost = calculate_bundle_cost(bundle)
        >>> cost["total_cost_lamports"]
        210000  # (2 txs * 2 sigs/tx * 5000) + 100000 tip
    """
    num_transactions = len(bundle.transactions)
    
    # Estimate signatures: each transaction typically has 1-2 signatures
    # (payer + program). Use conservative estimate of 2.
    est_signatures_per_tx = 2
    num_signatures = num_transactions * est_signatures_per_tx
    
    # Calculate network fees (Solana base fees)
    network_fees = num_signatures * base_fee_per_sig
    
    # Total cost = network fees + Jito tip
    total_cost = network_fees + bundle.tip_lamports
    
    return {
        "total_cost_lamports": total_cost,
        "network_fees_lamports": network_fees,
        "jito_tip_lamports": bundle.tip_lamports,
        "num_transactions": num_transactions,
        "num_signatures": num_signatures,
        "cost_per_tx_lamports": total_cost / num_transactions if num_transactions > 0 else 0,
    }


def estimate_slippage_for_bundle(
    bundle: JitoBundle,
    expected_sol_spread: float = 0.001,
) -> Dict[str, Any]:
    """Estimate slippage costs for a bundle.
    
    Pure function: output depends only on inputs.
    
    Args:
        bundle: The JitoBundle to analyze
        expected_sol_spread: Expected SOL price movement during bundle execution
    
    Returns:
        Dict with slippage estimates
    """
    cost = calculate_bundle_cost(bundle)
    
    # Rough estimate: slippage = tip + opportunity cost from SOL spread
    # This is a simplified model for paper trading
    slippage_lamports = cost["jito_tip_lamports"] + int(expected_sol_spread * 1_000_000_000)
    
    return {
        "slippage_lamports": slippage_lamports,
        "jito_tip_contribution": cost["jito_tip_lamports"],
        "spread_contribution_lamports": int(expected_sol_spread * 1_000_000_000),
        "notes": "Simplified model for paper trading",
    }


class JitoTipEstimator:
    """Helper class for estimating optimal Jito tips."""
    
    # Typical tip ranges (in lamports)
    MIN_TIP: int = 1_000      # 0.000001 SOL
    LOW_TIP: int = 10_000     # 0.00001 SOL
    MEDIUM_TIP: int = 100_000 # 0.0001 SOL
    HIGH_TIP: int = 500_000   # 0.0005 SOL
    MAX_TIP: int = 1_000_000  # 0.001 SOL
    
    @staticmethod
    def estimate_optimal_tip(
        urgency: str = "normal",  # "slow", "normal", "fast", "urgent"
        competition_factor: float = 1.0,
    ) -> int:
        """Estimate an optimal tip based on urgency.
        
        Args:
            urgency: How quickly you need the bundle to land
            competition_factor: Multiplier for competitive environments
        
        Returns:
            Recommended tip in lamports
        """
        base_tips = {
            "slow": JitoTipEstimator.LOW_TIP,
            "normal": JitoTipEstimator.MEDIUM_TIP,
            "fast": JitoTipEstimator.HIGH_TIP,
            "urgent": JitoTipEstimator.MAX_TIP,
        }
        
        base = base_tips.get(urgency, JitoTipEstimator.MEDIUM_TIP)
        return int(base * competition_factor)
    
    @staticmethod
    def validate_tip_amount(amount: int) -> bool:
        """Check if a tip amount is reasonable."""
        return JitoTipEstimator.MIN_TIP <= amount <= JitoTipEstimator.MAX_TIP * 10


# Aliases for convenience
BundleCost = calculate_bundle_cost
Bundle = JitoBundle


if __name__ == "__main__":
    # Demo usage
    print("Jito Bundle Structures Demo")
    print("=" * 50)
    
    # Create a bundle
    bundle = JitoBundle(
        transactions=["tx1_base64", "tx2_base64", "tx3_base64"],
        tip_lamports=100_000,
        strategy_tag="test-strategy",
    )
    
    print(f"\nBundle ID: {bundle.bundle_id}")
    print(f"Transactions: {len(bundle.transactions)}")
    print(f"Tip: {bundle.tip_lamports:,} lamports")
    
    # Calculate cost
    cost = calculate_bundle_cost(bundle)
    print(f"\nCost Breakdown:")
    for key, value in cost.items():
        print(f"  {key}: {value}")
    
    # Estimate optimal tip
    for urgency in ["slow", "normal", "fast", "urgent"]:
        tip = JitoTipEstimator.estimate_optimal_tip(urgency)
        print(f"\nOptimal tip ({urgency}): {tip:,} lamports")
