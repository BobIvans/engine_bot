"""
ingestion/dex/jupiter.py

Jupiter Quote API v6 Client.

PR-T.5
"""
import logging
import time
from typing import Any, Dict, List, Optional

import urllib.parse

from .models import QuoteResponse, RouteStep, SwapRequest, ErrorResponse

logger = logging.getLogger(__name__)


# Jupiter API Configuration
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"

# Retry configuration
MAX_RETRIES = 3
INITIAL_DELAY_MS = 100


class JupiterClient:
    """
    Client for Jupiter v6 Quote API.
    
    Features:
    - GET /quote endpoint for swap quotes
    - Automatic retry on HTTP 429
    - Graceful error handling
    - Route plan parsing
    
    PR-T.5
    """
    
    def __init__(
        self,
        base_url: str = JUPITER_QUOTE_URL,
        max_retries: int = MAX_RETRIES,
        initial_delay_ms: int = INITIAL_DELAY_MS,
    ):
        """
        Initialize JupiterClient.
        
        Args:
            base_url: Jupiter Quote API URL
            max_retries: Max retries for rate limiting
            initial_delay_ms: Initial delay for exponential backoff
        """
        self._base_url = base_url
        self._max_retries = max_retries
        self._initial_delay_ms = initial_delay_ms
    
    def _make_request(
        self,
        params: Dict[str, str],
        http_callable: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retries.
        
        Args:
            params: Query parameters
            http_callable: Optional HTTP callable for testing
            
        Returns:
            Response JSON
        """
        # Build URL
        query_string = urllib.parse.urlencode(params)
        url = f"{self._base_url}?{query_string}"
        
        delay_ms = self._initial_delay_ms
        last_error = None
        
        for attempt in range(self._max_retries + 1):
            try:
                if http_callable is not None:
                    response = http_callable(url, params)
                else:
                    import requests
                    resp = requests.get(url, timeout=30)
                    
                    # Check for rate limit
                    if resp.status_code == 429:
                        if attempt < self._max_retries:
                            time.sleep(delay_ms / 1000.0)
                            delay_ms *= 2
                            logger.warning(f"[jupiter] Rate limited, retrying in {delay_ms}ms")
                            continue
                        raise Exception("Rate limited after all retries")
                    
                    resp.raise_for_status()
                    response = resp.json()
                
                return response
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                if "429" in error_str or "rate limit" in error_str:
                    if attempt < self._max_retries:
                        time.sleep(delay_ms / 1000.0)
                        delay_ms *= 2
                        continue
                
                raise
        
        raise last_error
    
    def _parse_error(self, data: Dict[str, Any]) -> Optional[ErrorResponse]:
        """
        Parse error response.
        
        Args:
            data: Response data
            
        Returns:
            ErrorResponse if error found, None otherwise
        """
        if "error" in data:
            return ErrorResponse.from_dict(data)
        return None
    
    def _parse_route_plan(self, route_data: List[Dict[str, Any]]) -> List[RouteStep]:
        """
        Parse route plan from API response.
        
        Args:
            route_data: List of route step dicts
            
        Returns:
            List of RouteStep objects
        """
        steps = []
        for step_data in route_data:
            step = RouteStep(
                amm_key=step_data.get("ammKey", ""),
                label=step_data.get("label"),
                input_mint=step_data.get("inputMint", ""),
                output_mint=step_data.get("outputMint", ""),
                in_amount=int(step_data.get("inAmount", 0)),
                out_amount=int(step_data.get("outAmount", 0)),
            )
            steps.append(step)
        return steps
    
    def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        slippage_bps: int = 50,
        http_callable: Optional[Any] = None,
    ) -> Optional[QuoteResponse]:
        """
        Get a quote for a swap.
        
        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount_atomic: Amount in atomic units (integer)
            slippage_bps: Slippage tolerance in basis points
            http_callable: Optional HTTP callable for testing
            
        Returns:
            QuoteResponse or None if no route found
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount_atomic),
            "slippageBps": str(slippage_bps),
        }
        
        try:
            data = self._make_request(params, http_callable)
            
            # Check for error response
            error = self._parse_error(data)
            if error is not None:
                logger.warning(f"[jupiter] API error: {error.error}")
                if error.is_no_route_error():
                    return None
                return None
            
            # Parse route plan
            route_plan = self._parse_route_plan(data.get("routePlan", []))
            
            # Parse quote response
            quote = QuoteResponse(
                in_amount=int(data.get("inAmount", 0)),
                out_amount=int(data.get("outAmount", 0)),
                price_impact_pct=float(data.get("priceImpactPct", 0.0)),
                route_plan=route_plan,
                input_mint=input_mint,
                output_mint=output_mint,
                other_amount_threshold=int(data.get("otherAmountThreshold", 0)),
                slippage_bps=slippage_bps,
            )
            
            logger.debug(f"[jupiter] Quote: {quote.in_amount} -> {quote.out_amount} ({quote.price_impact_pct:.4%} impact)")
            return quote
            
        except Exception as e:
            logger.warning(f"[jupiter] Failed to get quote: {e}")
            return None
    
    def get_swap_quote(
        self,
        request: SwapRequest,
        http_callable: Optional[Any] = None,
    ) -> Optional[QuoteResponse]:
        """
        Get a quote for a swap using SwapRequest.
        
        Args:
            request: SwapRequest parameters
            http_callable: Optional HTTP callable for testing
            
        Returns:
            QuoteResponse or None if no route found
        """
        return self.get_quote(
            input_mint=request.input_mint,
            output_mint=request.output_mint,
            amount_atomic=request.amount_atomic,
            slippage_bps=request.slippage_bps,
            http_callable=http_callable,
        )
    
    def estimate_slippage(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        http_callable: Optional[Any] = None,
    ) -> Optional[int]:
        """
        Estimate slippage for a trade (in bps).
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount_atomic: Amount in atomic units
            http_callable: Optional HTTP callable for testing
            
        Returns:
            Price impact in bps, or None if quote failed
        """
        quote = self.get_quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount_atomic=amount_atomic,
            http_callable=http_callable,
        )
        
        if quote is None:
            return None
        
        return quote.get_price_impact_bps()
    
    def get_best_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        http_callable: Optional[Any] = None,
    ) -> Optional[QuoteResponse]:
        """
        Get the best quote (currently just calls get_quote, could be extended for routing).
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount_atomic: Amount in atomic units
            http_callable: Optional HTTP callable for testing
            
        Returns:
            Best QuoteResponse or None
        """
        return self.get_quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount_atomic=amount_atomic,
            http_callable=http_callable,
        )
    
    def check_route_availability(
        self,
        input_mint: str,
        output_mint: str,
        amount_atomic: int,
        http_callable: Optional[Any] = None,
    ) -> bool:
        """
        Check if a route exists for a swap.
        
        Args:
            input_mint: Input token mint
            output_mint: Output token mint
            amount_atomic: Amount in atomic units
            http_callable: Optional HTTP callable for testing
            
        Returns:
            True if route exists, False otherwise
        """
        quote = self.get_quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount_atomic=amount_atomic,
            http_callable=http_callable,
        )
        return quote is not None
