"""
ingestion/rpc/cache.py

RpcCache — simple in-memory TTL cache for RPC responses.
"""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Represents a cached value with TTL."""
    value: Any
    expires_at: float  # Unix timestamp


class RpcCache:
    """
    Simple in-memory TTL cache for RPC responses.
    
    Features:
    - Thread-safe operations
    - TTL-based expiration
    - No external dependencies (no Redis)
    
    PR-T.1
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialize RpcCache.
        
        Args:
            default_ttl: Default TTL for cache entries (seconds)
        """
        self._default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        
        # Metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            
            # Check if expired
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._evictions += 1
                self._misses += 1
                return None
            
            self._hits += 1
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (uses default if not provided)
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        
        with self._lock:
            self._cache[key] = CacheEntry(
                value=value,
                expires_at=time.time() + effective_ttl,
            )
    
    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        now = time.time()
        to_remove = []
        
        with self._lock:
            for key, entry in self._cache.items():
                if now > entry.expires_at:
                    to_remove.append(key)
            
            for key in to_remove:
                del self._cache[key]
        
        self._evictions += len(to_remove)
        return len(to_remove)
    
    def get_metrics(self) -> Dict[str, int]:
        """Get cache metrics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": len(self._cache),
                "hit_rate": self._hits / total if total > 0 else 0.0,
            }
    
    def get_size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists (and is not expired)."""
        return self.get(key) is not None
    
    def __len__(self) -> int:
        """Get cache size."""
        return self.get_size()
