"""
execution/routing/router.py

Multi-DEX Router Simulator for best execution.

Aggregates quotes from multiple liquidity sources and returns
ranked route candidates for optimal swap execution.

PR-U.4
"""
import sys
from typing import List, Optional
from execution.routing.interfaces import LiquiditySource
from execution.routing.types import SimulatedQuote, RouteCandidate


class LiquidityRouter:
    """
    Router that aggregates quotes from multiple liquidity sources.
    
    Supports parallel quote collection and best route selection.
    
    PR-U.4
    """
    
    def __init__(self):
        """Initialize an empty router."""
        self._sources: List[LiquiditySource] = []
        self._source_names: set = set()
    
    def register_source(self, source: LiquiditySource) -> None:
        """
        Register a liquidity source with the router.
        
        Args:
            source: LiquiditySource implementation
            
        Raises:
            ValueError: If source with same name already registered
        """
        name = source.get_name()
        if name in self._source_names:
            raise ValueError(f"Source '{name}' already registered")
        
        self._sources.append(source)
        self._source_names.add(name)
    
    def unregister_source(self, name: str) -> bool:
        """
        Unregister a liquidity source by name.
        
        Args:
            name: Source name to remove
            
        Returns:
            True if source was removed, False if not found
        """
        for i, source in enumerate(self._sources):
            if source.get_name() == name:
                self._sources.pop(i)
                self._source_names.remove(name)
                return True
        return False
    
    def get_registered_sources(self) -> List[str]:
        """
        Get list of registered source names.
        
        Returns:
            List of source names
        """
        return [s.get_name() for s in self._sources]
    
    def _collect_quote(self, source: LiquiditySource, mint_in: str, mint_out: str, amount_in: int) -> Optional[RouteCandidate]:
        """
        Collect quote from a single source with error handling.
        
        Args:
            source: LiquiditySource to query
            mint_in: Input token mint
            mint_out: Output token mint
            amount_in: Input amount
            
        Returns:
            RouteCandidate or None if quote fails
        """
        try:
            quote = source.get_quote(mint_in, mint_out, amount_in)
            if quote is None:
                return None
            
            return RouteCandidate(
                quote=quote,
                source_name=source.get_name(),
                is_local_calc=getattr(source, '_is_local_calc', True),
            )
        except Exception as e:
            # Fail-safe: log error and continue
            print(f"[router] WARNING: {source.get_name()} failed: {e}", file=sys.stderr)
            return None
    
    def get_all_quotes(
        self,
        mint_in: str,
        mint_out: str,
        amount_in: int,
    ) -> List[RouteCandidate]:
        """
        Get quotes from all registered sources.
        
        Args:
            mint_in: Input token mint address
            mint_out: Output token mint address
            amount_in: Input amount in atomic units
            
        Returns:
            List of RouteCandidate (may be empty if all sources fail)
        """
        results: List[RouteCandidate] = []
        
        for source in self._sources:
            candidate = self._collect_quote(source, mint_in, mint_out, amount_in)
            if candidate is not None:
                results.append(candidate)
        
        return results
    
    def find_best_route(
        self,
        mint_in: str,
        mint_out: str,
        amount_in: int,
    ) -> Optional[RouteCandidate]:
        """
        Find the best route for swapping.
        
        Best route is defined as the one with highest amount_out.
        
        Args:
            mint_in: Input token mint address
            mint_out: Output token mint address
            amount_in: Input amount in atomic units
            
        Returns:
            Best RouteCandidate or None if no quotes available
        """
        all_quotes = self.get_all_quotes(mint_in, mint_out, amount_in)
        
        if not all_quotes:
            return None
        
        # Sort by amount_out descending (best execution first)
        all_quotes.sort(key=lambda x: x.amount_out, reverse=True)
        
        return all_quotes[0]
    
    def compare_routes(self, mint_in: str, mint_out: str, amount_in: int) -> str:
        """
        Generate a comparison string of all routes.
        
        Useful for logging/debugging.
        
        Args:
            mint_in: Input token mint
            mint_out: Output token mint
            amount_in: Input amount
            
        Returns:
            Human-readable comparison string
        """
        quotes = self.get_all_quotes(mint_in, mint_out, amount_in)
        
        if not quotes:
            return "[router] No quotes available"
        
        # Sort for display
        sorted_quotes = sorted(quotes, key=lambda x: x.amount_out, reverse=True)
        
        parts = []
        for q in sorted_quotes:
            parts.append(f"{q.source_name}({q.amount_out})")
        
        return " vs ".join(parts)
