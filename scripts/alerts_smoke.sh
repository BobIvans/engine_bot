#!/bin/bash
# scripts/alerts_smoke.sh
# PR-D.4 Monitoring & Telegram Alerts - Mocked Smoke Test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[alerts_smoke] Starting alerts smoke test..." >&2

# Python test script
python3 << PYTHON_TEST
import sys
import os
import tempfile
from unittest.mock import patch, MagicMock

# Add root to path
sys.path.insert(0, '$ROOT_DIR')

# Set mock environment variables
os.environ["TELEGRAM_BOT_TOKEN"] = "mock_token"
os.environ["TELEGRAM_CHAT_ID"] = "mock_chat_id"

# Test counters
passed = 0
failed = 0

def test_case(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [alerts] {name}: PASS", file=sys.stderr)
        passed += 1
    else:
        print(f"  [alerts] {name}: FAIL {msg}", file=sys.stderr)
        failed += 1

print("[alerts_smoke] Testing TelegramBot...", file=sys.stderr)

# Test 1: TelegramBot initialization from env
from monitoring.alerts import TelegramBot, send_alert, compose_signal_alert

bot = TelegramBot.from_env()
test_case("bot_init_env", bot.token == "mock_token" and bot.chat_id == "mock_chat_id")

# Test 2: send_message with mocked requests
with patch('monitoring.alerts.requests') as mock_requests:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_requests.Session.return_value.post.return_value = mock_response

    result = bot.send_message("Test message", level="INFO")
    test_case("send_message_success", result == True)

    # Verify the correct URL was called
    call_args = mock_requests.Session.return_value.post.call_args
    url = call_args[0][0]
    test_case("send_message_url", "api.telegram.org" in url, f"got {url}")

    # Verify payload
    payload = call_args[1].get('json', {})
    test_case("send_message_payload", payload.get('chat_id') == "mock_chat_id")
    test_case("send_message_text", "Test message" in payload.get('text', ''))

print("[alerts_smoke] Testing message composition...", file=sys.stderr)

# Test 3: compose_signal_alert
from monitoring.alerts import compose_signal_alert, compose_kill_switch_alert, compose_error_alert

signal = {
    "mint": "So11111111111111111111111111111111111111112",
    "price": 0.001234,
    "size_usd": 100.50,
    "wallet": "Wallet123456789",
    "mode": "U",
}

buy_msg = compose_signal_alert(signal, alert_type="BUY")
test_case("compose_buy_signal", "🟢" in buy_msg and "ENTER" in buy_msg)
test_case("buy_has_mint", "So111" in buy_msg)  # Truncated mint
test_case("buy_has_price", "0.001234" in buy_msg)

sell_msg = compose_signal_alert(signal, alert_type="SELL")
test_case("compose_sell_signal", "🔴" in sell_msg and "EXIT" in sell_msg)

# Test 4: compose_kill_switch_alert
kill_msg = compose_kill_switch_alert("Max drawdown exceeded", "25% drawdown")
test_case("kill_switch_alert", "🚨" in kill_msg and "KILL-SWITCH" in kill_msg)
test_case("kill_switch_reason", "Max drawdown" in kill_msg)

# Test 5: compose_error_alert
error_msg = compose_error_alert("RPC Timeout", "Connection refused", "Wallet: ABC")
test_case("error_alert", "❌" in error_msg and "Critical Error" in error_msg)

print("[alerts_smoke] Testing metrics export...", file=sys.stderr)

# Test 6: export_run_metrics
from monitoring.exporters import export_run_metrics, flatten_metrics

# Create temp directory
with tempfile.TemporaryDirectory() as tmpdir:
    metrics_path = os.path.join(tmpdir, "test_metrics.csv")
    
    # Nested metrics
    metrics = {
        "session": {
            "pnl": 100.50,
            "winrate": 0.65,
        },
        "trades": 42,
        "equity": {
            "start": 10000.0,
            "current": 10100.50,
        }
    }
    
    result = export_run_metrics(metrics, metrics_path)
    test_case("export_csv_success", result == True)
    test_case("export_csv_file_exists", os.path.exists(metrics_path))
    
    # Verify file contents
    with open(metrics_path, 'r') as f:
        content = f.read()
        test_case("export_csv_has_header", "timestamp" in content)
        test_case("export_csv_has_pnl", "session_pnl" in content)
        test_case("export_csv_flattened", "equity_current" in content)

# Test 7: send_alert convenience function
print("[alerts_smoke] Testing send_alert function...", file=sys.stderr)

with patch('monitoring.alerts.requests') as mock_requests:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_requests.Session.return_value.post.return_value = mock_response

    result = send_alert("Test alert", level="WARNING")
    test_case("send_alert_success", result == True)

# Test 8: TelegramBot with missing env vars
print("[alerts_smoke] Testing fail-safe behavior...", file=sys.stderr)

# Temporarily unset env vars
old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
old_chat = os.environ.pop("TELEGRAM_CHAT_ID", None)

try:
    bot_no_env = TelegramBot.from_env()
    # Should return a dummy bot
    test_case("fail_safe_no_env", bot_no_env.token == "")

finally:
    # Restore env vars
    if old_token:
        os.environ["TELEGRAM_BOT_TOKEN"] = old_token
    if old_chat:
        os.environ["TELEGRAM_CHAT_ID"] = old_chat

# Test 9: flatten_metrics
flat = flatten_metrics({"a": {"b": 1, "c": {"d": 2}}, "e": 3})
test_case("flatten_simple", flat.get("a_b") == 1)
test_case("flatten_nested", flat.get("a_c_d") == 2)
test_case("flatten_flat", flat.get("e") == 3)

# Summary
print(f"\n[alerts_smoke] Tests: {passed} passed, {failed} failed", file=sys.stderr)

if failed > 0:
    sys.exit(1)
else:
    print("[alerts_smoke] OK ✅", file=sys.stderr)
    sys.exit(0)
PYTHON_TEST

echo "[alerts_smoke] Smoke test completed." >&2
