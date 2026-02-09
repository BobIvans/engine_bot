"""
ingestion/rpc/batcher.py

RpcBatcher — queues requests and batches them for efficient RPC calls.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BatchItem:
    """Represents a single RPC request in a batch."""
    method: str
    params: list
    callback: Callable[[Any], None]
    key: str = ""
    ttl: int = 300


class BatchFuture:
    """A future-like object to hold the result of a batched request."""
    def __init__(self):
        self._result = None
        self._ready = threading.Event()
    
    def set_result(self, value: Any):
        self._result = value
        self._ready.set()
    
    def get(self, timeout: Optional[float] = None) -> Any:
        self._ready.wait(timeout=timeout)
        return self._result


class RpcBatcher:
    """
    Batches RPC requests for efficient transmission.
    
    Features:
    - Queues requests and flushes when batch is full (MAX_BATCH_SIZE)
    - Timer-based flushing (batch_delay_ms) for smaller batches
    - Thread-safe operation
    
    PR-T.1
    """
    
    MAX_BATCH_SIZE = 100  # Per Solana JSON RPC spec
    
    def __init__(
        self,
        max_batch_size: int = MAX_BATCH_SIZE,
        batch_delay_ms: float = 10.0,
        http_callable: Optional[Callable[[list], list]] = None,
    ):
        """
        Initialize RpcBatcher.
        
        Args:
            max_batch_size: Maximum items per batch
            batch_delay_ms: Max delay before flushing (milliseconds)
            http_callable: Function to execute batched requests
        """
        self._max_batch_size = max_batch_size
        self._batch_delay_ms = batch_delay_ms
        self._http_callable = http_callable
        
        self._queue: List[BatchItem] = []
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._last_flush_time = 0.0
        
        # Metrics
        self._batches_sent = 0
        self._requests_batched = 0
        
    def queue_request(self, item: BatchItem) -> BatchFuture:
        """
        Queue a request for batching.
        
        Args:
            item: The batch item to queue
            
        Returns:
            BatchFuture that will hold the result
        """
        future = BatchFuture()
        item.callback = future.set_result  # Wrap callback to use future
        
        with self._lock:
            self._queue.append(item)
            
            # Check if we should flush
            if len(self._queue) >= self._max_batch_size:
                self._flush()
            elif self._timer is None:
                # Start timer for delayed flush
                self._timer = threading.Timer(
                    self._batch_delay_ms / 1000.0,
                    self._on_timer,
                )
                self._timer.start()
        
        return future
    
    def _on_timer(self) -> None:
        """Called when timer expires - flush the batch."""
        with self._lock:
            if self._queue:
                self._flush()
            self._timer = None
    
    def _flush(self) -> None:
        """Execute the current batch."""
        if not self._queue:
            return
        
        # Take all items from queue
        items = self._queue
        self._queue = []
        
        # Cancel timer if active
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        
        self._last_flush_time = time.time()
        
        # Execute batch if callable provided
        if self._http_callable:
            try:
                responses = self._http_callable(items)
                self._batches_sent += 1
                self._requests_batched += len(items)
                
                # Dispatch responses
                for item, response in zip(items, responses):
                    try:
                        item.callback(response)
                    except Exception as e:
                        logger.error(f"[batcher] Error in callback: {e}")
                        
            except Exception as e:
                logger.error(f"[batcher] Batch execution failed: {e}")
                # Signal error to all futures
                for item in items:
                    item.callback(e)
    
    def flush(self) -> None:
        """Manually flush any pending requests."""
        with self._lock:
            if self._queue:
                self._flush()
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        with self._lock:
            return len(self._queue)
    
    def get_metrics(self) -> Dict[str, int]:
        """Get batcher metrics."""
        return {
            "batches_sent": self._batches_sent,
            "requests_batched": self._requests_batched,
            "pending_requests": len(self._queue),
        }
    
    def __del__(self):
        """Cleanup timer on destruction."""
        if self._timer is not None:
            self._timer.cancel()
