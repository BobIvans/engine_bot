"""execution/queues.py

PR-D.3 Execution Queues & Rate Limiting.

Provides concurrency control layer for trading signals:
- RateLimiter: Token bucket / sliding window rate limiting
- SignalQueue: Priority queue for signal ordering

Design goals:
- Free-first: In-memory implementation (no Redis required)
- Deterministic: Injectable clock for testing
- Priority-aware: SELL > BUY signal ordering
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Priority constants (lower = higher priority)
PRIORITY_CRITICAL = 0  # Kill-switch / Liquidation
PRIORITY_EXIT = 10  # TP/SL exits
PRIORITY_ENTRY = 50  # New positions


@dataclass
class RateLimiter:
    """Token bucket rate limiter with injectable clock.

    Attributes:
        limit: Maximum requests per window.
        window_sec: Time window in seconds.
        clock: Callable returning current time (defaults to time.time).
    """

    limit: int
    window_sec: float
    clock: Any = None

    def __post_init__(self):
        if self.clock is None:
            self.clock = time.time
        self._tokens: Dict[str, float] = {}  # key -> available tokens
        self._last_refill: Dict[str, float] = {}  # key -> last refill timestamp

    def can_proceed(self, key: str) -> bool:
        """Check if a request can proceed under rate limits.

        Args:
            key: Identifier for rate limit bucket (e.g., "rpc:helius", "dex:raydium")

        Returns:
            True if request is within rate limits, False if rate limited.
        """
        now = self.clock()
        tokens = self._tokens.get(key, float(self.limit))
        last_refill = self._last_refill.get(key, now)

        # Calculate tokens since last refill
        elapsed = now - last_refill
        tokens = min(float(self.limit), tokens + elapsed * (self.limit / self.window_sec))

        if tokens >= 1.0:
            # Consume one token
            self._tokens[key] = tokens - 1.0
            self._last_refill[key] = now
            return True

        # Not enough tokens
        self._tokens[key] = tokens
        self._last_refill[key] = now
        return False

    def get_wait_time(self, key: str) -> float:
        """Get time until next token is available.

        Args:
            key: Identifier for rate limit bucket.

        Returns:
            Seconds to wait for next token (0 if available now).
        """
        now = self.clock()
        tokens = self._tokens.get(key, float(self.limit))
        last_refill = self._last_refill.get(key, now)

        elapsed = now - last_refill
        tokens = min(float(self.limit), tokens + elapsed * (self.limit / self.window_sec))

        if tokens >= 1.0:
            return 0.0

        # Calculate time to get one token
        deficit = 1.0 - tokens
        rate = self.limit / self.window_sec
        return deficit / rate

    def reset(self, key: str) -> None:
        """Reset rate limit state for a key.

        Args:
            key: Identifier for rate limit bucket.
        """
        self._tokens.pop(key, None)
        self._last_refill.pop(key, None)


class SignalQueue:
    """Priority queue for trading signals.

    Wraps queue.PriorityQueue with priority support.
    Lower priority number = higher priority (SELLs before BUYs).

    Attributes:
        max_size: Maximum queue size (None = unlimited).
    """

    def __init__(self, max_size: Optional[int] = None):
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_size or 0)
        self.max_size = max_size
        self._counter = 0  # For FIFO ordering within same priority

    def push(self, signal: Dict[str, Any], priority: int = PRIORITY_ENTRY) -> bool:
        """Push a signal onto the queue.

        Args:
            signal: Signal dictionary to queue.
            priority: Priority value (lower = higher priority).

        Returns:
            True if pushed successfully, False if queue is full.

        Note:
            SELL signals (priority=10) will be processed before
            BUY signals (priority=50).
        """
        try:
            if self.max_size is not None and self._queue.qsize() >= self.max_size:
                return False
            # PriorityQueue expects (priority, counter, data) tuple
            # Use counter to break ties (FIFO for same priority)
            self._counter += 1
            self._queue.put_nowait((priority, self._counter, signal))
            return True
        except queue.Full:
            return False

    def pop(self) -> Optional[Dict[str, Any]]:
        """Pop the highest priority signal from the queue.

        Returns:
            Signal dictionary or None if queue is empty.
        """
        try:
            priority, counter, signal = self._queue.get_nowait()
            return signal
        except queue.Empty:
            return None

    def peek(self) -> Optional[Dict[str, Any]]:
        """Peek at the highest priority signal without removing it.

        Returns:
            Signal dictionary or None if queue is empty.
        """
        try:
            priority, counter, signal = self._queue.queue[0]
            return signal
        except (queue.Empty, IndexError):
            return None

    def size(self) -> int:
        """Get current queue size.

        Returns:
            Number of signals in queue.
        """
        return self._queue.qsize()

    def empty(self) -> bool:
        """Check if queue is empty.

        Returns:
            True if queue is empty.
        """
        return self._queue.empty()

    def full(self) -> bool:
        """Check if queue is full.

        Returns:
            True if queue has reached max size.
        """
        if self.max_size is None:
            return False
        return self._queue.qsize() >= self.max_size

    def clear(self) -> None:
        """Remove all signals from queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def get_all(self) -> list[Dict[str, Any]]:
        """Drain and return all signals in priority order.

        Returns:
            List of all signals in queue (empty if none).
        """
        signals = []
        while not self._queue.empty():
            try:
                priority, counter, signal = self._queue.get_nowait()
                signals.append(signal)
            except queue.Empty:
                break
        return signals


class RateLimitedSignalQueue:
    """Combined queue with rate limiting.

    Wraps SignalQueue with RateLimiter for provider protection.

    Attributes:
        queue: Underlying SignalQueue.
        limiter: RateLimiter for RPC/DEX protection.
    """

    def __init__(
        self,
        max_queue_size: Optional[int] = None,
        rate_limit: int = 10,
        rate_window: float = 1.0,
        clock: Any = None,
    ):
        self.queue = SignalQueue(max_size=max_queue_size)
        self.limiter = RateLimiter(limit=rate_limit, window_sec=rate_window, clock=clock)

    def push(
        self,
        signal: Dict[str, Any],
        priority: int = PRIORITY_ENTRY,
        provider_key: str = "default",
    ) -> bool:
        """Push a signal with rate limit check.

        Args:
            signal: Signal dictionary.
            priority: Signal priority.
            provider_key: Rate limit bucket key.

        Returns:
            True if pushed, False if rate limited or queue full.
        """
        if not self.limiter.can_proceed(provider_key):
            return False
        return self.queue.push(signal, priority)

    def push_bypass(self, signal: Dict[str, Any], priority: int = PRIORITY_ENTRY) -> bool:
        """Push a signal bypassing rate limits (for SELLs).

        Args:
            signal: Signal dictionary.
            priority: Signal priority.

        Returns:
            True if pushed, False if queue full.
        """
        return self.queue.push(signal, priority)

    def pop(self) -> Optional[Dict[str, Any]]:
        """Pop the highest priority signal.

        Returns:
            Signal or None.
        """
        return self.queue.pop()

    def size(self) -> int:
        """Get queue size."""
        return self.queue.size()

    def empty(self) -> bool:
        """Check if empty."""
        return self.queue.empty()

    def full(self) -> bool:
        """Check if full."""
        return self.queue.full()

    def get_wait_time(self, provider_key: str) -> float:
        """Get wait time for provider."""
        return self.limiter.get_wait_time(provider_key)
