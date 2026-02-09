"""
execution/routing/types.py

Data structures for Multi-DEX Router Simulator.

PR-U.4
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class SimulatedQuote:
    """
    Simulated quote result from a liquidity source.
    
    Represents the output of a swap simulation for a given input amount.
    
    PR-U.4
    """
    mint_in: str           # Input token mint (base58)
    mint_out: str          # Output token mint (base58)
    amount_in: int         # Input amount in atomic units (lamports/wasabi)
    amount_out: int        # Output amount in atomic units
    price_impact_bps: int  # Price impact in basis points (1 bps = 0.01%)
    fee_atomic: int        # Fee paid in atomic units of input token
    
    @property
    def price_impact_pct(self) -> float:
        """Return price impact as percentage."""
        return self.price_impact_bps / 100.0
    
    @property
    def amount_in_display(self) -> float:
        """Return amount in human-readable format (simplified)."""
        return self.amount_in / 1e9  # Assuming 9 decimals for display
    
    @property
    def amount_out_display(self) -> float:
        """Return amount in human-readable format (simplified)."""
        return self.amount_out / 1e9  # Assuming 9 decimals for display


@dataclass
class RouteCandidate:
    """
    A route candidate for swap execution.
    
    Wraps a SimulatedQuote with metadata about the source.
    
    PR-U.4
    """
    quote: SimulatedQuote
    source_name: str       # e.g., "raydium_v4", "jupiter_api", "meteora_dlmm"
    is_local_calc: bool    # True if calculated locally, False if from API
    raw_tx_hint: Optional[str] = None  # Optional transaction hint for debugging
    
    @property
    def amount_out(self) -> int:
        """Access amount_out from the underlying quote."""
        return self.quote.amount_out
    
    @property
    def effective_price(self) -> float:
        """Calculate effective price (output per input)."""
        if self.quote.amount_in == 0:
            return 0.0
        return self.quote.amount_out / self.quote.amount_in
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source_name,
            "is_local": self.is_local_calc,
            "amount_in": self.quote.amount_in,
            "amount_out": self.quote.amount_out,
            "price_impact_bps": self.quote.price_impact_bps,
            "fee_atomic": self.quote.fee_atomic,
            "effective_price": self.effective_price,
        }
