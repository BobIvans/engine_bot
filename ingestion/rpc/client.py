"""
ingestion/rpc/client.py

SmartRpcClient — unified facade for RPC calls with batching, caching, and failover.
"""
import logging
from typing import Any, Callable, Dict, List, Optional
import time

from .batcher import RpcBatcher, BatchItem, BatchFuture
from .cache import RpcCache
from .failover import FailoverManager

logger = logging.getLogger(__name__)


class SmartRpcClient:
    """
    Unified RPC client with batching, caching, and failover.
    
    Supports:
    - Batching of requests (max 100 per batch, per Solana JSON RPC spec)
    - TTL-based caching (Mint info → forever/24h, Balance/Price → per-block)
    - Free-tier safety with exponential backoff on 429 errors
    - Failover between multiple RPC providers
    
    PR-T.1, PR-T.2
    """
    
    # Cache TTL policies (seconds)
    TTL_MINT_INFO = 86400       # 24 hours for mint decimals, authority
    TTL_BALANCE = 1             # 1 second (per-block) for balances
    TTL_PRICE = 2               # 2 seconds for prices
    
    # Batch configuration
    MAX_BATCH_SIZE = 100        # Per Solana JSON RPC spec
    
    def __init__(
        self,
        http_callable: Optional[Callable[[list], List[Any]]] = None,
        cache_ttl: int = 300,
        batch_delay_ms: float = 10.0,
        max_retries: int = 5,
        initial_delay_ms: float = 100.0,
        failover_manager: Optional[FailoverManager] = None,
    ):
        """
        Initialize SmartRpcClient.
        
        Args:
            http_callable: Function to execute batched HTTP calls (optional for deferred mode)
            cache_ttl: Default TTL for cache entries (seconds)
            batch_delay_ms: Max delay before flushing batch (milliseconds)
            max_retries: Max retries for 429 errors
            initial_delay_ms: Initial delay for exponential backoff (ms)
            failover_manager: Optional FailoverManager instance
        """
        self._http_callable = http_callable
        self._cache = RpcCache(default_ttl=cache_ttl)
        self._batcher = RpcBatcher(
            max_batch_size=self.MAX_BATCH_SIZE,
            batch_delay_ms=batch_delay_ms,
            http_callable=self._execute_batch if http_callable else None,
        )
        self._max_retries = max_retries
        self._initial_delay_ms = initial_delay_ms
        self._failover_manager = failover_manager
        
        # Metrics for monitoring
        self._http_calls = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._failover_count = 0
        
        # Pending requests awaiting flush
        self._pending_futures: List[Any] = []
        
    def set_failover_manager(self, manager: FailoverManager) -> None:
        """Set the failover manager."""
        self._failover_manager = manager
        
    def _execute_batch(self, items: List[BatchItem]) -> List[Any]:
        """
        Execute batch with failover support.
        """
        if self._http_callable is None:
            raise RuntimeError("No HTTP callable provided for batch execution")
        
        delay_ms = self._initial_delay_ms
        last_error = None
        attempted_endpoints = set()
        
        # Get list of available endpoints
        endpoints = []
        if self._failover_manager is not None:
            endpoints = self._failover_manager.get_endpoints()
        else:
            # Default endpoint if no failover
            endpoints = ["default"]
        
        # Try each endpoint in order
        for endpoint in endpoints:
            # Skip already failed endpoints
            if endpoint in attempted_endpoints:
                continue
            
            # Build request list with this endpoint
            requests = []
            for item in items:
                requests.append({
                    'method': item.method,
                    'params': item.params,
                    'endpoint': endpoint,
                })
            
            for attempt in range(self._max_retries + 1):
                try:
                    responses = self._http_callable(requests)
                    self._http_calls += 1
                    
                    # Cache each response and report success
                    for item, response in zip(items, responses):
                        self._cache.set(item.key, response, ttl=item.ttl)
                    
                    # Report success to failover manager
                    if self._failover_manager is not None:
                        self._failover_manager.report_success(endpoint)
                    
                    return responses
                    
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    
                    # Report failure to failover manager
                    if self._failover_manager is not None:
                        self._failover_manager.report_failure(endpoint)
                    
                    # Check for rate limit (429)
                    if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
                        if attempt < self._max_retries:
                            time.sleep(delay_ms / 1000.0)
                            delay_ms *= 2
                            continue
                    
                    # For other errors, break to try next endpoint
                    attempted_endpoints.add(endpoint)
                    self._failover_count += 1
                    logger.warning(f"[rpc] Failed on {endpoint}, trying next endpoint...")
                    break
            
            # If we got here, this endpoint failed, try next one
            if last_error is not None:
                continue
        
        # All endpoints failed
        raise last_error if last_error else RuntimeError("All endpoints failed")
    
    def _get_ttl_for_method(self, method: str) -> int:
        """Get TTL based on RPC method."""
        if method in ("getMint", "getAccountInfo"):  # Mint info (decimals, authority)
            return self.TTL_MINT_INFO
        elif method == "getBalance":
            return self.TTL_BALANCE
        elif method == "getPrice":
            return self.TTL_PRICE
        return self._cache.default_ttl
    
    def request(
        self,
        method: str,
        params: list,
        key: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> Any:
        """
        Make an RPC request with batching, caching, and failover.
        
        Args:
            method: RPC method name (e.g., "getBalance")
            params: RPC parameters
            key: Cache key (auto-generated from method+params if not provided)
            ttl: Cache TTL override (seconds)
            
        Returns:
            RPC response result
        """
        # Generate cache key if not provided
        if key is None:
            key = f"{method}:{params}"
        
        # Check cache first
        cached = self._cache.get(key)
        if cached is not None:
            self._cache_hits += 1
            logger.debug(f"[rpc] Cache hit for {method}")
            # Return a pre-resolved future for cache hits
            future = BatchFuture()
            future.set_result(cached)
            return future
        
        self._cache_misses += 1
        
        # Determine TTL
        effective_ttl = ttl if ttl is not None else self._get_ttl_for_method(method)
        
        # Create wrapper callback that returns the result
        result_holder: Dict[str, Any] = {"value": None}
        
        def callback(response: Any):
            result_holder["value"] = response
        
        item = BatchItem(
            method=method,
            params=params,
            callback=callback,
            key=key,
            ttl=effective_ttl,
        )
        
        future = self._batcher.queue_request(item)
        self._pending_futures.append(future)
        
        # Return the future for async usage
        return future
    
    def flush(self) -> List[Any]:
        """
        Flush all pending batched requests.
        
        Returns:
            List of results from all pending requests
        """
        # Flush the batcher
        self._batcher.flush()
        
        # Collect all results
        results = []
        for future in self._pending_futures:
            results.append(future.get())
        
        self._pending_futures.clear()
        return results
    
    def request_all(
        self,
        requests: List[Dict[str, Any]],
    ) -> List[Any]:
        """
        Make multiple RPC requests in a single batch.
        
        Args:
            requests: List of dicts with 'method', 'params', 'key', 'ttl'
            
        Returns:
            List of results
        """
        futures = []
        
        for req in requests:
            method = req.get('method')
            params = req.get('params', [])
            key = req.get('key', f"{method}:{params}")
            ttl = req.get('ttl')
            
            future = self.request(method, params, key=key, ttl=ttl)
            futures.append(future)
        
        return self.flush()
    
    def get_balance(self, pubkey: str) -> int:
        """Get token balance for an account."""
        future = self.request("getBalance", [pubkey])
        self.flush()
        return future.get()
    
    def get_mint_info(self, mint: str) -> Dict[str, Any]:
        """Get mint information (decimals, authority)."""
        future = self.request("getAccountInfo", [mint])
        self.flush()
        return future.get()
    
    def get_multiple_accounts(self, pubkeys: list) -> Dict[str, Any]:
        """Get multiple account info in batch."""
        future = self.request("getMultipleAccounts", [pubkeys])
        self.flush()
        return future.get()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get client metrics."""
        total = self._cache_hits + self._cache_misses
        return {
            "http_calls": self._http_calls,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": (
                self._cache_hits / total
                if total > 0
                else 0.0
            ),
            "failover_count": self._failover_count,
        }
    
    def clear_cache(self) -> None:
        """Clear the cache."""
        self._cache.clear()
