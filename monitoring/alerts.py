"""monitoring/alerts.py

PR-D.4 Telegram Alerts.

Telegram bot client for sending notifications:
- BUY/SELL fills
- Kill-switch activation
- Critical errors

Design goals:
- Zero secrets in code (env vars only)
- Fail-safe (never crash pipeline on alert failure)
- Strict timeouts (prevent blocking)
- Clean stdout (logs to stderr)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


# Alert levels (emoji prefixes)
ALERT_INFO = "INFO"
ALERT_WARNING = "WARNING"
ALERT_ERROR = "ERROR"
ALERT_CRITICAL = "CRITICAL"


@dataclass
class TelegramBot:
    """Telegram bot client for sending alerts.

    Attributes:
        token: Bot token from TELEGRAM_BOT_TOKEN env var.
        chat_id: Chat ID from TELEGRAM_CHAT_ID env var.
        timeout: Request timeout in seconds (default: 3).
    """

    token: str
    chat_id: str
    timeout: int = 3
    _session: Optional[requests.Session] = None

    @classmethod
    def from_env(cls, timeout: int = 3) -> "TelegramBot":
        """Create bot from environment variables."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            print("[TelegramBot] Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set", file=sys.stderr)
            # Return a dummy bot that logs but doesn't send
            return cls(token="", chat_id="", timeout=timeout)

        return cls(token=token, chat_id=chat_id, timeout=timeout)

    def _get_session(self) -> requests.Session:
        """Get or create a session."""
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def send_message(
        self,
        text: str,
        level: str = ALERT_INFO,
        disable_notification: bool = False,
    ) -> bool:
        """Send a message to the configured chat.

        Args:
            text: Message text to send.
            level: Alert level for emoji prefix.
            disable_notification: Mute the message.

        Returns:
            True if sent successfully, False otherwise.
        """
        # Validate config
        if not self.token or not self.chat_id:
            print(f"[TelegramBot] Would send (disabled): {text[:50]}...", file=sys.stderr)
            return False

        # Format message with emoji prefix
        emoji = self._get_level_emoji(level)
        formatted_text = f"{emoji} {text}"

        payload = {
            "chat_id": self.chat_id,
            "text": formatted_text,
            "parse_mode": "Markdown",
            "disable_notification": disable_notification,
        }

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        try:
            session = self._get_session()
            response = session.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            print(f"[TelegramBot] Sent: {text[:50]}...", file=sys.stderr)
            return True

        except requests.exceptions.Timeout:
            print(f"[TelegramBot] Timeout sending message: {text[:50]}...", file=sys.stderr)
            return False
        except requests.exceptions.RequestException as e:
            print(f"[TelegramBot] Request failed: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"[TelegramBot] Unexpected error: {e}", file=sys.stderr)
            return False

    def _get_level_emoji(self, level: str) -> str:
        """Get emoji for alert level."""
        emojis = {
            ALERT_INFO: "ℹ️",
            ALERT_WARNING: "⚠️",
            ALERT_ERROR: "❌",
            ALERT_CRITICAL: "🚨",
        }
        return emojis.get(level, "ℹ️")


def compose_signal_alert(
    signal: Dict[str, Any],
    alert_type: str = "BUY",
) -> str:
    """Compose a readable alert message for a signal.

    Args:
        signal: Signal dictionary with trade details.
        alert_type: Type of signal (BUY/SELL).

    Returns:
        Formatted message string.
    """
    mint = signal.get("mint", "UNKNOWN")[:10]
    price = signal.get("price", 0)
    size_usd = signal.get("size_usd", 0)
    wallet = signal.get("wallet", "UNKNOWN")[:8]
    mode = signal.get("mode", "-")

    if alert_type == "BUY":
        emoji = "🟢"
        action = "ENTER"
    elif alert_type == "SELL":
        emoji = "🔴"
        action = "EXIT"
    else:
        emoji = "⚪"
        action = alert_type.upper()

    return (
        f"{emoji} *{action} Signal*\n"
        f"• Token: `{mint}`\n"
        f"• Price: `${price:.6f}`\n"
        f"• Size: `${size_usd:.2f}`\n"
        f"• Wallet: `{wallet}`\n"
        f"• Mode: `{mode}`"
    )


def compose_kill_switch_alert(reason: str, details: str = "") -> str:
    """Compose a kill-switch activation alert.

    Args:
        reason: Reason for kill-switch activation.
        details: Additional details.

    Returns:
        Formatted message string.
    """
    message = f"🚨 *KILL-SWITCH ACTIVATED*\n• Reason: `{reason}`"
    if details:
        message += f"\n• Details: `{details}`"
    return message


def compose_error_alert(error_type: str, message: str, context: str = "") -> str:
    """Compose a critical error alert.

    Args:
        error_type: Type of error.
        message: Error message.
        context: Additional context.

    Returns:
        Formatted message string.
    """
    msg = f"❌ *Critical Error*\n• Type: `{error_type}`\n• Message: `{message}`"
    if context:
        msg += f"\n• Context: `{context}`"
    return msg


# PR-X.1: Balance discrepancy alert type
ALERT_BALANCE_DISCREPANCY = "balance_discrepancy"


def compose_balance_discrepancy_alert(
    delta_lamports: int,
    onchain_balance: int,
    local_balance: int,
    reason: str,
    adjusted: bool,
) -> str:
    """Compose a balance discrepancy alert.

    Args:
        delta_lamports: Difference between onchain and local (lamports).
        onchain_balance: Actual on-chain balance (lamports).
        local_balance: Local portfolio balance (lamports).
        reason: Reason for discrepancy.
        adjusted: Whether adjustment was applied.

    Returns:
        Formatted message string.
    """
    delta_sol = delta_lamports / 1_000_000_000
    onchain_sol = onchain_balance / 1_000_000_000
    local_sol = local_balance / 1_000_000_000
    
    emoji = "⚠️" if abs(delta_sol) < 0.01 else "🚨"
    status = "✅ Adjusted" if adjusted else "❌ Not adjusted"
    
    return (
        f"{emoji} *Balance Discrepancy*\n"
        f"• On-chain: `{onchain_sol:.9f}` SOL\n"
        f"• Local: `{local_sol:.9f}` SOL\n"
        f"• Delta: `{delta_sol:+.9f}` SOL\n"
        f"• Reason: `{reason}`\n"
        f"• Status: {status}"
    )


def send_alert(
    text: str,
    level: str = ALERT_INFO,
    bot: Optional[TelegramBot] = None,
) -> bool:
    """Convenience function to send an alert.

    Args:
        text: Alert message.
        level: Alert level.
        bot: Optional TelegramBot instance (creates one from env if None).

    Returns:
        True if sent successfully.
    """
    if bot is None:
        bot = TelegramBot.from_env()

    return bot.send_message(text, level)
