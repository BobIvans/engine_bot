"""
Jupiter Quote API v6 Adapter

Optional adapter for fetching route quotes from the public Jupiter Aggregator API v6.
Provides both real API integration and deterministic fixture-based operation.

Free-Tier Alignment:
- Uses ONLY public Quote API without authentication
- Rate limits: ≤3 requests/sec (implemented via time.sleep(0.35) between requests)
- Fixture for all tests

Graceful Degradation:
- On API unavailability (429/5xx/timeout) → log to stderr + return None
- Pipeline continues without Jupiter quotes
"""

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Constants
JUPITER_API_BASE = "https://quote-api.jup.ag/v6/quote"
SOL_MINT = "So11111111111111111111111111111111111111112"
DEFAULT_SLIPPAGE_BPS = 50
CACHE_TTL_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.35


@dataclass
class SwapInfo:
    """Canonical swap info from route plan."""
    amm_key: str
    label: str
    input_mint: str
    output_mint: str


@dataclass
class RoutePlanStep:
    """Single step in route plan."""
    swap_info: SwapInfo


@dataclass
class JupiterRoute:
    """
    Normalized Jupiter route in canonical jupiter_route.v1 format.
    
    Attributes:
        route_id: Deterministic hash-based identifier
        in_mint: Input token mint address
        out_mint: Output token mint address
        in_amount: Input amount in base units (string for precision)
        out_amount: Output amount in base units (string for precision)
        price_impact_pct: Price impact percentage (0-100)
        route_plan: List of DEX hops
        context_slot: Solana slot when quote was computed
        time_taken_ms: Time taken to compute quote in milliseconds
    """
    route_id: str
    in_mint: str
    out_mint: str
    in_amount: str
    out_amount: str
    price_impact_pct: float
    route_plan: List[RoutePlanStep]
    context_slot: int
    time_taken_ms: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "route_id": self.route_id,
            "in_mint": self.in_mint,
            "out_mint": self.out_mint,
            "in_amount": self.in_amount,
            "out_amount": self.out_amount,
            "price_impact_pct": self.price_impact_pct,
            "route_plan": [
                {
                    "swap_info": {
                        "amm_key": step.swap_info.amm_key,
                        "label": step.swap_info.label,
                        "input_mint": step.swap_info.input_mint,
                        "output_mint": step.swap_info.output_mint,
                    }
                }
                for step in self.route_plan
            ],
            "context_slot": self.context_slot,
            "time_taken_ms": self.time_taken_ms,
        }

    @property
    def route_hops(self) -> int:
        """Number of DEX hops in route."""
        return len(self.route_plan)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JupiterRoute":
        """Create from dictionary."""
        return cls(
            route_id=data["route_id"],
            in_mint=data["in_mint"],
            out_mint=data["out_mint"],
            in_amount=data["in_amount"],
            out_amount=data["out_amount"],
            price_impact_pct=data["price_impact_pct"],
            route_plan=[
                RoutePlanStep(
                    swap_info=SwapInfo(
                        amm_key=step["swap_info"]["amm_key"],
                        label=step["swap_info"]["label"],
                        input_mint=step["swap_info"]["input_mint"],
                        output_mint=step["swap_info"]["output_mint"],
                    )
                )
                for step in data["route_plan"]
            ],
            context_slot=data["context_slot"],
            time_taken_ms=data["time_taken_ms"],
        )


class CacheEntry:
    """Cache entry with TTL tracking."""
    
    def __init__(self, route: JupiterRoute, timestamp: datetime):
        self.route = route
        self.timestamp = timestamp
    
    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return datetime.now() - self.timestamp < timedelta(seconds=CACHE_TTL_SECONDS)


class JupiterQuoteFetcher:
    """
    Fetches Jupiter route quotes from API or fixtures.
    
    Features:
    - Deterministic fixture mode for testing
    - In-memory caching (10 second TTL)
    - Graceful degradation on API errors
    - Rate limiting for free-tier compliance
    """
    
    def __init__(self, cache_ttl: int = CACHE_TTL_SECONDS):
        self.cache: Dict[Tuple[str, str, str], CacheEntry] = {}
        self.cache_ttl = cache_ttl
        self._session = requests.Session()
    
    def _make_cache_key(self, in_mint: str, out_mint: str, in_amount: str) -> Tuple[str, str, str]:
        """Create cache key from quote parameters."""
        return (in_mint, out_mint, in_amount)
    
    def _get_cached(self, in_mint: str, out_mint: str, in_amount: str) -> Optional[JupiterRoute]:
        """Retrieve cached quote if valid."""
        key = self._make_cache_key(in_mint, out_mint, in_amount)
        entry = self.cache.get(key)
        if entry and entry.is_valid():
            return entry.route
        return None
    
    def _set_cached(self, in_mint: str, out_mint: str, in_amount: str, route: JupiterRoute) -> None:
        """Cache a successful quote."""
        key = self._make_cache_key(in_mint, out_mint, in_amount)
        self.cache[key] = CacheEntry(route, datetime.now())
    
    def _clear_cache(self) -> None:
        """Clear all cached entries."""
        self.cache.clear()
    
    def normalize_quote(
        self,
        raw: Dict[str, Any],
        in_mint: str,
        out_mint: str,
        in_amount: str,
    ) -> JupiterRoute:
        """
        Normalize raw Jupiter API response to canonical format.
        
        Args:
            raw: Raw API response dictionary
            in_mint: Expected input mint (validated against response)
            out_mint: Expected output mint (validated against response)
            in_amount: Expected input amount (validated against response)
            
        Returns:
            Normalized JupiterRoute
            
        Raises:
            ValueError: On validation failure
        """
        # Validate input/output mints match expected
        if raw.get("inputMint") != in_mint:
            raise ValueError(f"inputMint mismatch: expected {in_mint}, got {raw.get('inputMint')}")
        if raw.get("outputMint") != out_mint:
            raise ValueError(f"outputMint mismatch: expected {out_mint}, got {raw.get('outputMint')}")
        if raw.get("inAmount") != in_amount:
            raise ValueError(f"inAmount mismatch: expected {in_amount}, got {raw.get('inAmount')}")
        
        # Extract values
        raw_in_mint = raw["inputMint"]
        raw_out_mint = raw["outputMint"]
        raw_in_amount = raw["inAmount"]
        raw_out_amount = raw["outAmount"]
        raw_price_impact = float(raw.get("priceImpactPct", "0"))
        raw_context_slot = int(raw.get("contextSlot", 0))
        raw_time_taken = int(raw.get("timeTaken", 0))
        
        # Validate outputs
        if int(raw_out_amount) <= 0:
            raise ValueError(f"Invalid out_amount: {raw_out_amount}")
        if raw_price_impact < 0:
            raise ValueError(f"Invalid price_impact_pct: {raw_price_impact}")
        
        # Transform route_plan to canonical format
        route_plan = []
        for step in raw.get("routePlan", []):
            swap_info_raw = step.get("swapInfo", {})
            swap_info = SwapInfo(
                amm_key=swap_info_raw.get("ammKey", ""),
                label=swap_info_raw.get("label", "Unknown"),
                input_mint=swap_info_raw.get("inputMint", ""),
                output_mint=swap_info_raw.get("outputMint", ""),
            )
            route_plan.append(RoutePlanStep(swap_info=swap_info))
        
        # Generate deterministic route_id
        route_id_source = f"{raw_in_mint}:{raw_out_mint}:{raw_in_amount}:{raw_context_slot}"
        route_id = hashlib.sha256(route_id_source.encode()).hexdigest()[:16]
        
        return JupiterRoute(
            route_id=route_id,
            in_mint=raw_in_mint,
            out_mint=raw_out_mint,
            in_amount=raw_in_amount,
            out_amount=raw_out_amount,
            price_impact_pct=raw_price_impact,
            route_plan=route_plan,
            context_slot=raw_context_slot,
            time_taken_ms=raw_time_taken,
        )
    
    def load_from_file(self, path: str, in_mint: str, out_mint: str, in_amount: str) -> Optional[JupiterRoute]:
        """
        Load and normalize quote from fixture file.
        
        Args:
            path: Path to JSON fixture file
            in_mint: Expected input mint
            out_mint: Expected output mint
            in_amount: Expected input amount
            
        Returns:
            Normalized JupiterRoute or None on error
        """
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            return self.normalize_quote(raw, in_mint, out_mint, in_amount)
        except FileNotFoundError:
            print(f"[jupiter_quote] ERROR: Fixture file not found: {path}", file=sys.stderr)
            return None
        except json.JSONDecodeError as e:
            print(f"[jupiter_quote] ERROR: Invalid JSON in fixture: {e}", file=sys.stderr)
            return None
        except ValueError as e:
            print(f"[jupiter_quote] ERROR: Fixture validation failed: {e}", file=sys.stderr)
            return None
    
    def fetch_quote(
        self,
        in_mint: str,
        out_mint: str,
        in_amount: str,
        allow_jupiter: bool = False,
        use_cache: bool = True,
    ) -> Optional[JupiterRoute]:
        """
        Fetch quote from Jupiter API or cache.
        
        Args:
            in_mint: Input token mint address
            out_mint: Output token mint address
            in_amount: Input amount in base units
            allow_jupiter: Whether to allow real API calls
            use_cache: Whether to use cached results
            
        Returns:
            Normalized JupiterRoute or None on failure/unavailable
        """
        if not allow_jupiter:
            return None
        
        # Check cache first
        if use_cache:
            cached = self._get_cached(in_mint, out_mint, in_amount)
            if cached:
                return cached
        
        # Build API URL
        params = {
            "inputMint": in_mint,
            "outputMint": out_mint,
            "amount": in_amount,
            "slippageBps": DEFAULT_SLIPPAGE_BPS,
        }
        
        try:
            # Rate limiting for free-tier compliance
            time.sleep(REQUEST_DELAY_SECONDS)
            
            response = self._session.get(JUPITER_API_BASE, params=params, timeout=10)
            response.raise_for_status()
            
            raw = response.json()
            
            # Normalize response
            route = self.normalize_quote(raw, in_mint, out_mint, in_amount)
            
            # Cache successful result
            if use_cache:
                self._set_cached(in_mint, out_mint, in_amount, route)
            
            return route
            
        except requests.exceptions.Timeout:
            print(f"[jupiter_quote] WARNING: API timeout for {in_mint} -> {out_mint}", file=sys.stderr)
            return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print(f"[jupiter_quote] WARNING: Rate limited (429)", file=sys.stderr)
            else:
                print(f"[jupiter_quote] WARNING: HTTP error {e.response.status_code}", file=sys.stderr)
            return None
        except requests.exceptions.RequestException as e:
            print(f"[jupiter_quote] WARNING: Request failed: {e}", file=sys.stderr)
            return None
        except ValueError as e:
            print(f"[jupiter_quote] WARNING: Normalization failed: {e}", file=sys.stderr)
            return None
    
    def get_best_route_for_token(
        self,
        token_mint: str,
        sol_amount: str,
        allow_jupiter: bool = False,
    ) -> Optional[JupiterRoute]:
        """
        Get best route for buying token with SOL.
        
        Wrapper method for common buy token on SOL use case.
        
        Args:
            token_mint: Token mint to buy
            sol_amount: Amount of SOL in base units (lamports)
            allow_jupiter: Whether to allow real API calls
            
        Returns:
            Normalized JupiterRoute or None
        """
        return self.fetch_quote(
            in_mint=SOL_MINT,
            out_mint=token_mint,
            in_amount=sol_amount,
            allow_jupiter=allow_jupiter,
        )


def run_cli():
    """CLI interface for Jupiter Quote Fetcher."""
    parser = argparse.ArgumentParser(
        description="Jupiter Quote API v6 Adapter - Fetch or simulate token swap routes"
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Path to fixture JSON file (for offline mode)",
    )
    parser.add_argument(
        "--in-mint",
        type=str,
        default=SOL_MINT,
        help="Input token mint address",
    )
    parser.add_argument(
        "--out-mint",
        type=str,
        required=True,
        help="Output token mint address",
    )
    parser.add_argument(
        "--amount",
        type=str,
        required=True,
        help="Input amount in base units",
    )
    parser.add_argument(
        "--allow-jupiter",
        action="store_true",
        default=False,
        help="Allow real API calls to Jupiter (disabled by default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixture without side effects",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Output summary as single-line JSON to stdout",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear cached quotes before fetching",
    )
    
    args = parser.parse_args()
    
    fetcher = JupiterQuoteFetcher()
    
    # Clear cache if requested
    if args.clear_cache:
        fetcher._clear_cache()
    
    route = None
    
    # Try fixture first if specified
    if args.input_file:
        route = fetcher.load_from_file(args.input_file, args.in_mint, args.out_mint, args.amount)
        if route:
            print(f"[jupiter_quote] Loaded fixture: {args.input_file}", file=sys.stderr)
    
    # Try API if allowed and no fixture
    if not route and args.allow_jupiter:
        route = fetcher.fetch_quote(
            args.in_mint,
            args.out_mint,
            args.amount,
            allow_jupiter=True,
        )
        if route:
            print(f"[jupiter_quote] Fetched from API: {args.in_mint} -> {args.out_mint}", file=sys.stderr)
    
    if not route:
        print("[jupiter_quote] ERROR: No quote available", file=sys.stderr)
        sys.exit(1)
    
    # Log route details
    out_amount_val = int(route.out_amount)
    price_per_token = out_amount_val / 1e9 if route.out_mint != SOL_MINT else out_amount_val / 1e9
    print(
        f"[jupiter_quote] Route: {route.in_amount[:8]}... -> {route.out_amount[:8]}... "
        f"({route.route_hops} hop(s), impact={route.price_impact_pct:.2f}%)",
        file=sys.stderr,
    )
    
    if args.summary_json:
        summary = {
            "quote_success": True,
            "out_amount": route.out_amount,
            "price_impact_pct": route.price_impact_pct,
            "route_hops": route.route_hops,
            "schema_version": "jupiter_route.v1",
        }
        print(json.dumps(summary))
    elif args.dry_run:
        print(json.dumps(route.to_dict(), indent=2))
    
    return route


if __name__ == "__main__":
    run_cli()
