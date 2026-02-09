"""ops/panic.py

PR-Z.1 Master Kill-Switch (Panic Button)

Emergency stop mechanism for immediate strategy shutdown:
- Stops new signal generation
- Cancels pending orders (if possible)
- Closes open positions at market (or hard SL)
- Blocks further actions until manual reset

Activation via flag file (default /tmp/strategy_panic.flag)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

# Configure logging to stderr only (no print() in ops/)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.CRITICAL)

# Default flag path
DEFAULT_PANIC_FLAG_PATH = "/tmp/strategy_panic.flag"

# Cache for panic state (avoid repeated file I/O)
_panic_cache: Optional[bool] = None
_panic_cache_time: float = 0.0


def is_panic_active(
    flag_path: str = DEFAULT_PANIC_FLAG_PATH,
    cache_ttl_seconds: float = 0.0,
) -> bool:
    """Check if panic mode is active.

    Fast check (< 1ms) using optional caching.

    Args:
        flag_path: Path to panic flag file.
        cache_ttl_seconds: Cache TTL in seconds. 0 = no cache.

    Returns:
        True if panic is active, False otherwise.
    """
    global _panic_cache, _panic_cache_time

    import time

    # Check cache if TTL > 0
    if cache_ttl_seconds > 0 and _panic_cache is not None:
        if time.time() - _panic_cache_time < cache_ttl_seconds:
            return _panic_cache

    # Check if flag file exists
    try:
        is_active = os.path.exists(flag_path)
    except (OSError, PermissionError):
        # On error, default to safe state (no panic)
        logger.warning(f"panic: Failed to check flag at {flag_path}, defaulting to inactive")
        return False

    # Update cache
    if cache_ttl_seconds > 0:
        _panic_cache = is_active
        _panic_cache_time = time.time()

    return is_active


def get_panic_reason(
    flag_path: str = DEFAULT_PANIC_FLAG_PATH,
) -> Optional[str]:
    """Read panic reason from flag file.

    Args:
        flag_path: Path to panic flag file.

    Returns:
        Panic reason string if file exists and contains text, None otherwise.
    """
    if not os.path.exists(flag_path):
        return None

    try:
        with open(flag_path, "r") as f:
            content = f.read().strip()
            return content if content else "Master kill-switch activated"
    except (OSError, PermissionError):
        return "Master kill-switch activated (reason unreadable)"


def create_panic_flag(
    flag_path: str = DEFAULT_PANIC_FLAG_PATH,
    reason: str = "Manual activation",
) -> None:
    """Create panic flag file (for testing/automation).

    Args:
        flag_path: Path to create flag file.
        reason: Reason for panic activation.
    """
    # Create parent directory if needed
    os.makedirs(os.path.dirname(flag_path), exist_ok=True)

    with open(flag_path, "w") as f:
        f.write(reason)


def clear_panic_flag(flag_path: str = DEFAULT_PANIC_FLAG_PATH) -> bool:
    """Remove panic flag file.

    Args:
        flag_path: Path to panic flag file.

    Returns:
        True if successfully removed, False otherwise.
    """
    try:
        if os.path.exists(flag_path):
            os.remove(flag_path)
            return True
    except (OSError, PermissionError):
        pass
    return False


def clear_panic_cache() -> None:
    """Clear the panic cache to force fresh check."""
    global _panic_cache, _panic_cache_time
    _panic_cache = None
    _panic_cache_time = 0.0


class PanicShutdown(Exception):
    """Exception raised when panic mode is activated.

    Used to immediately halt execution with proper cleanup.
    """
    def __init__(self, reason: str = "Master kill-switch activated"):
        self.reason = reason
        super().__init__(reason)


def require_no_panic(
    flag_path: str = DEFAULT_PANIC_FLAG_PATH,
) -> None:
    """Check that panic is not active, raise PanicShutdown if it is.

    Args:
        flag_path: Path to panic flag file.

    Raises:
        PanicShutdown: If panic is active.
    """
    if is_panic_active(flag_path):
        reason = get_panic_reason(flag_path) or "Unknown"
        logger.critical(f"PANIC ACTIVATED: {reason}")
        raise PanicShutdown(reason)


# Self-test
if __name__ == "__main__":
    import tempfile
    import time

    print("=== Panic Module Self-Test ===", file=sys.stderr)

    # Use temp path for testing
    test_flag = tempfile.mktemp(suffix="_panic_test.flag")

    # Test 1: No flag initially
    print(f"\nTest 1: No flag at {test_flag}", file=sys.stderr)
    assert not is_panic_active(test_flag), "Flag should not exist"
    assert get_panic_reason(test_flag) is None, "No reason should be returned"
    print("  is_panic_active = False (expected)", file=sys.stderr)
    print("  get_panic_reason = None (expected)", file=sys.stderr)

    # Test 2: Create flag
    print(f"\nTest 2: Create flag at {test_flag}", file=sys.stderr)
    create_panic_flag(test_flag, "Test panic activation")
    assert is_panic_active(test_flag), "Flag should exist"
    reason = get_panic_reason(test_flag)
    assert reason == "Test panic activation", f"Expected 'Test panic activation', got '{reason}'"
    print(f"  is_panic_active = True (expected)", file=sys.stderr)
    print(f"  reason = '{reason}' (expected)", file=sys.stderr)

    # Test 3: Clear flag
    print(f"\nTest 3: Clear flag at {test_flag}", file=sys.stderr)
    assert clear_panic_flag(test_flag), "Should return True"
    assert not is_panic_active(test_flag), "Flag should not exist"
    print("  Flag cleared successfully", file=sys.stderr)
    print("  is_panic_active = False (expected)", file=sys.stderr)

    # Test 4: PanicShutdown exception
    print("\nTest 4: PanicShutdown exception", file=sys.stderr)
    create_panic_flag(test_flag, "Test exception")
    try:
        require_no_panic(test_flag)
        assert False, "Should have raised PanicShutdown"
    except PanicShutdown as e:
        print(f"  PanicShutdown raised: '{e.reason}'", file=sys.stderr)
    finally:
        clear_panic_flag(test_flag)

    # Test 5: Cache behavior
    print("\nTest 5: Cache behavior", file=sys.stderr)
    create_panic_flag(test_flag, "Cache test")
    clear_panic_cache()
    # First call populates cache
    is_active = is_panic_active(test_flag, cache_ttl_seconds=60.0)
    # File deleted but cache still shows True
    os.remove(test_flag)
    is_cached = is_panic_active(test_flag, cache_ttl_seconds=60.0)
    assert is_active == True, "First call should return True"
    assert is_cached == True, "Cached value should still be True"
    print("  Cache working correctly", file=sys.stderr)
    clear_panic_cache()

    print("\n=== All tests passed! ===", file=sys.stderr)
