"""ops/kill_switch.py

PR-Z.1 Master Kill-Switch Integration

Integrates panic mechanism with execution pipeline:
- Checks panic state before each action
- Provides force_close_all_positions() for emergency closure
- Graceful shutdown handling

Usage:
    from ops.kill_switch import check_panic, force_close_all

    # At start of each tick/loop:
    check_panic()

    # For force close all positions:
    await force_close_all_positions(executor, order_manager)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional

from ops.panic import (
    is_panic_active,
    get_panic_reason,
    require_no_panic,
    PanicShutdown,
    DEFAULT_PANIC_FLAG_PATH,
)

# Configure logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.CRITICAL)


# Default config (can be overridden via config loading)
DEFAULT_CONFIG = {
    "enabled": True,
    "flag_path": DEFAULT_PANIC_FLAG_PATH,
    "on_panic": "close_all_market",  # "close_all_market" | "hard_stop" | "set_sl"
    "cache_ttl_seconds": 0.0,  # 0 = no cache for safety
}


class KillSwitchConfig:
    """Configuration for kill switch behavior."""

    def __init__(
        self,
        enabled: bool = True,
        flag_path: str = DEFAULT_PANIC_FLAG_PATH,
        on_panic: str = "close_all_market",
        cache_ttl_seconds: float = 0.0,
    ):
        self.enabled = enabled
        self.flag_path = flag_path
        self.on_panic = on_panic
        self.cache_ttl_seconds = cache_ttl_seconds


def check_panic(
    config: Optional[KillSwitchConfig] = None,
) -> None:
    """Check panic state and raise if active.

    Call at start of each tick/loop cycle.

    Args:
        config: Kill switch configuration. Uses defaults if None.

    Raises:
        PanicShutdown: If panic is active.
    """
    if config is None:
        config = KillSwitchConfig()

    if not config.enabled:
        return

    try:
        require_no_panic(config.flag_path)
    except PanicShutdown:
        raise


async def force_close_all_positions(
    executor: Any,
    order_manager: Any,
    reason: str = "PANIC: Emergency close",
) -> list[dict]:
    """Force close all open positions.

    Args:
        executor: Live executor for executing closes.
        order_manager: Order manager with open positions.
        reason: Reason for force close.

    Returns:
        List of close results.
    """
    results = []

    if order_manager is None:
        logger.warning("kill_switch: No order_manager, cannot close positions")
        return results

    # Get all open positions
    open_positions = [
        pos_id for pos_id, pos in order_manager._positions.items()
        if pos.status.value == "open"
    ]

    logger.critical(f"kill_switch: Force closing {len(open_positions)} positions")

    for pos_id in open_positions:
        try:
            action = order_manager.force_close(pos_id, reason)
            if action and action.success:
                results.append({
                    "position_id": pos_id,
                    "success": True,
                    "action": action,
                })
                logger.info(f"kill_switch: Closed position {pos_id}")
            else:
                results.append({
                    "position_id": pos_id,
                    "success": False,
                    "action": action,
                })
                logger.error(f"kill_switch: Failed to close position {pos_id}")
        except Exception as e:
            results.append({
                "position_id": pos_id,
                "success": False,
                "error": str(e),
            })
            logger.exception(f"kill_switch: Error closing position {pos_id}")

    return results


def cancel_all_pending_orders(
    executor: Any,
    order_manager: Any,
) -> int:
    """Cancel all pending orders.

    Args:
        executor: Live executor for canceling orders.
        order_manager: Order manager with pending orders.

    Returns:
        Number of orders canceled.
    """
    # This would be implemented based on the specific executor interface
    # For now, return 0 as placeholder
    logger.warning("kill_switch: cancel_all_pending_orders not fully implemented")
    return 0


class KillSwitch:
    """Main kill switch integration class.

    Usage:
        ks = KillSwitch(config=kill_config)

        # In main loop:
        ks.check()  # Raises on panic

        # On panic:
        await ks.emergency_shutdown(executor, order_manager)
    """

    def __init__(
        self,
        config: Optional[KillSwitchConfig] = None,
    ):
        self.config = config or KillSwitchConfig()

    def check(self) -> None:
        """Check panic state. Raises on panic."""
        check_panic(self.config)

    def get_status(self) -> dict:
        """Get kill switch status.

        Returns:
            Dict with enabled, active, reason keys.
        """
        active = is_panic_active(self.config.flag_path)
        reason = get_panic_reason(self.config.flag_path) if active else None

        return {
            "enabled": self.config.enabled,
            "active": active,
            "reason": reason,
            "flag_path": self.config.flag_path,
            "on_panic": self.config.on_panic,
        }

    async def emergency_shutdown(
        self,
        executor: Any,
        order_manager: Any,
    ) -> dict:
        """Perform emergency shutdown.

        Args:
            executor: Live executor.
            order_manager: Order manager.

        Returns:
            Dict with shutdown results.
        """
        result = {
            "panic_active": True,
            "reason": get_panic_reason(self.config.flag_path) or "Unknown",
            "positions_closed": 0,
            "orders_canceled": 0,
            "errors": [],
        }

        logger.critical(f"PANIC EMERGENCY SHUTDOWN: {result['reason']}")

        # Cancel pending orders
        try:
            result["orders_canceled"] = cancel_all_pending_orders(executor, order_manager)
        except Exception as e:
            result["errors"].append(f"Cancel orders: {str(e)}")

        # Force close positions
        try:
            close_results = await force_close_all_positions(
                executor, order_manager, "PANIC: Emergency shutdown"
            )
            result["positions_closed"] = sum(1 for r in close_results if r.get("success"))
        except Exception as e:
            result["errors"].append(f"Close positions: {str(e)}")

        logger.critical(
            f"PANIC SHUTDOWN COMPLETE: "
            f"{result['positions_closed']} closed, "
            f"{result['orders_canceled']} canceled"
        )

        return result


def load_kill_switch_config(config_dict: dict) -> KillSwitchConfig:
    """Load kill switch config from dict.

    Args:
        config_dict: Dict with panic configuration.

    Returns:
        KillSwitchConfig instance.
    """
    panic_cfg = config_dict.get("panic", {})
    return KillSwitchConfig(
        enabled=panic_cfg.get("enabled", True),
        flag_path=panic_cfg.get("flag_path", DEFAULT_PANIC_FLAG_PATH),
        on_panic=panic_cfg.get("on_panic", "close_all_market"),
        cache_ttl_seconds=panic_cfg.get("cache_ttl_seconds", 0.0),
    )


# Self-test
if __name__ == "__main__":
    import tempfile

    print("=== Kill Switch Self-Test ===", file=sys.stderr)

    test_flag = tempfile.mktemp(suffix="_kill_test.flag")

    # Test 1: Default config
    print("\nTest 1: Default config", file=sys.stderr)
    config = KillSwitchConfig()
    assert config.enabled == True
    assert config.flag_path == DEFAULT_PANIC_FLAG_PATH
    assert config.on_panic == "close_all_market"
    print("  Default config created", file=sys.stderr)

    # Test 2: Custom config
    print("\nTest 2: Custom config", file=sys.stderr)
    custom_config = KillSwitchConfig(
        enabled=False,
        flag_path=test_flag,
        on_panic="hard_stop",
    )
    assert custom_config.enabled == False
    assert custom_config.flag_path == test_flag
    print("  Custom config created", file=sys.stderr)

    # Test 3: Load from dict
    print("\nTest 3: Load from dict", file=sys.stderr)
    config_dict = {
        "panic": {
            "enabled": True,
            "flag_path": test_flag,
            "on_panic": "set_sl",
            "cache_ttl_seconds": 1.0,
        }
    }
    loaded = load_kill_switch_config(config_dict)
    assert loaded.enabled == True
    assert loaded.flag_path == test_flag
    assert loaded.on_panic == "set_sl"
    print("  Config loaded from dict", file=sys.stderr)

    # Test 4: Status check
    print("\nTest 4: Status check", file=sys.stderr)
    ks = KillSwitch(config=KillSwitchConfig(flag_path=test_flag, enabled=False))
    status = ks.get_status()
    assert status["enabled"] == False
    assert status["active"] == False
    print(f"  Status: {status}", file=sys.stderr)

    # Clean up
    if os.path.exists(test_flag):
        os.remove(test_flag)

    print("\n=== All tests passed! ===", file=sys.stderr)
