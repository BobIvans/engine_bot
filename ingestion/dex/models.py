"""
ingestion/dex/models.py

Jupiter Quote API response models.

PR-T.5
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RouteStep:
    """A single step in the swap route."""
    amm_key: str              # Pool/AMM identifier
    label: Optional[str]      # Human-readable label (e.g., "Raydium", "Orca")
    input_mint: str          # Input token mint address
    output_mint: str         # Output token mint address
    in_amount: int           # Input amount (atomic units)
    out_amount: int          # Output amount (atomic units)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "amm_key": self.amm_key,
            "label": self.label,
            "input_mint": self.input_mint,
            "output_mint": self.output_mint,
            "in_amount": self.in_amount,
            "out_amount": self.out_amount,
        }


@dataclass
class QuoteResponse:
    """
    Normalized Jupiter Quote API response.
    
    PR-T.5
    """
    # Input/Output amounts (atomic units - integers)
    in_amount: int           # Amount in (atomic units)
    out_amount: int          # Amount out (atomic units)
    
    # Price impact (percentage as float, e.g., 0.001 = 0.1%)
    price_impact_pct: float
    
    # Route information
    route_plan: List[RouteStep]
    
    # Token info
    input_mint: str
    output_mint: str
    
    # Additional data (optional)
    other_amount_threshold: int = 0
    slippage_bps: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "in_amount": self.in_amount,
            "out_amount": self.out_amount,
            "price_impact_pct": self.price_impact_pct,
            "route_plan": [step.to_dict() for step in self.route_plan],
            "input_mint": self.input_mint,
            "output_mint": self.output_mint,
            "other_amount_threshold": self.other_amount_threshold,
            "slippage_bps": self.slippage_bps,
        }
    
    def get_out_amount_decimal(self, decimals: int = 6) -> float:
        """Get output amount in decimal format."""
        return self.out_amount / (10 ** decimals)
    
    def get_in_amount_decimal(self, decimals: int = 9) -> float:
        """Get input amount in decimal format (default SOL = 9 decimals)."""
        return self.in_amount / (10 ** decimals)
    
    def get_price_impact_bps(self) -> int:
        """Get price impact in basis points (1% = 100 bps)."""
        return int(self.price_impact_pct * 10000)
    
    def is_slippage_acceptable(self, max_slippage_bps: int = 100) -> bool:
        """Check if price impact is within acceptable slippage."""
        return self.get_price_impact_bps() <= max_slippage_bps
    
    def get_dexes_used(self) -> List[str]:
        """Get list of DEXes used in the route."""
        dexes = []
        for step in self.route_plan:
            if step.label and step.label not in dexes:
                dexes.append(step.label)
        return dexes
    
    def is_multi_dex_route(self) -> bool:
        """Check if route uses multiple DEXes."""
        return len(self.get_dexes_used()) > 1


@dataclass
class SwapRequest:
    """Request parameters for a Jupiter swap."""
    input_mint: str          # Input token mint
    output_mint: str        # Output token mint
    amount_atomic: int      # Amount in atomic units
    slippage_bps: int = 50  # Slippage tolerance in bps (default 0.5%)
    
    def to_url_params(self) -> Dict[str, str]:
        """Convert to URL query parameters."""
        return {
            "inputMint": self.input_mint,
            "outputMint": self.output_mint,
            "amount": str(self.amount_atomic),
            "slippageBps": str(self.slippage_bps),
        }


@dataclass
class ErrorResponse:
    """Error response from Jupiter API."""
    error: str
    error_code: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorResponse":
        return cls(
            error=data.get("error", "Unknown error"),
            error_code=data.get("errorCode"),
        )
    
    def is_no_route_error(self) -> bool:
        """Check if this is a 'no route found' error."""
        no_route_keywords = ["no route", "no available route", "cannot fulfill"]
        return any(kw.lower() in self.error.lower() for kw in no_route_keywords)
