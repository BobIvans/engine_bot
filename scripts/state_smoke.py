#!/usr/bin/env python3
"""Smoke test for Portfolio State Manager (PR-B.6).

Tests state transitions (entry, exit, cooldown) using pure functions
from strategy/state_update.py.

Usage:
    python scripts/state_smoke.py
    bash scripts/state_smoke.sh

Exit codes:
    - 0: All test cases passed
    - 1: One or more test cases failed
"""

import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.state import PortfolioState, StateUpdateParams
from strategy.state_update import (
    transition_on_entry,
    transition_on_exit,
    update_cooldown,
    reset_daily_pnl,
)


def run_state_smoke_tests():
    """Run state transition smoke tests from JSONL fixture."""
    script_dir = Path(__file__).parent
    fixture_path = script_dir / ".." / "integration" / "fixtures" / "state" / "transitions.jsonl"
    
    print("[state_smoke] Starting state transition tests...", file=sys.stderr)
    
    all_passed = True
    test_count = 0
    passed_count = 0
    
    try:
        with open(fixture_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                test_count += 1
                test_case = json.loads(line)
                case_id = test_case["case_id"]
                description = test_case.get("description", "")
                
                # Parse test case
                initial_bankroll = test_case["initial_bankroll"]
                params_dict = test_case.get("params", {})
                events = test_case["events"]
                expected = test_case["expected"]
                
                # Create params
                params = StateUpdateParams(
                    max_daily_loss_usd=params_dict.get("max_daily_loss_usd", 500.0),
                    cooldown_duration_sec=params_dict.get("cooldown_duration_sec", 3600),
                )
                
                # Initialize state
                state = PortfolioState.initial(initial_bankroll_usd=initial_bankroll, now_ts=0)
                
                entry_blocked = False
                
                # Process events
                for event in events:
                    event_type = event.get("event_type")
                    ts = event.get("ts", 0)
                    
                    if event_type == "entry":
                        new_state, error = transition_on_entry(
                            state=state,
                            signal_id=event["signal_id"],
                            token_mint=event["token_mint"],
                            wallet_address=event["wallet_address"],
                            size_usd=event["size_usd"],
                            fill_price=event["fill_price"],
                            now_ts=ts,
                            params=params,
                        )
                        if error:
                            entry_blocked = True
                        else:
                            state = new_state
                    
                    elif event_type == "exit":
                        state, error = transition_on_exit(
                            state=state,
                            signal_id=event["signal_id"],
                            token_mint=event["token_mint"],
                            wallet_address=event["wallet_address"],
                            exit_price=event["exit_price"],
                            pnl_usd=event["pnl_usd"],
                            now_ts=ts,
                        )
                    
                    elif event_type == "entry_attempt":
                        # This is an entry that should fail due to cooldown
                        new_state, error = transition_on_entry(
                            state=state,
                            signal_id=event["signal_id"],
                            token_mint=event["token_mint"],
                            wallet_address=event["wallet_address"],
                            size_usd=event["size_usd"],
                            fill_price=event["fill_price"],
                            now_ts=ts,
                            params=params,
                        )
                        if error:
                            entry_blocked = True
                        else:
                            state = new_state
                    
                    # Update cooldown after each event
                    state = update_cooldown(state, params, ts)
                
                # Verify expected results
                passed = True
                failures = []
                
                if abs(state.bankroll_usd - expected.get("bankroll_usd", state.bankroll_usd)) > 0.01:
                    passed = False
                    failures.append(f"bankroll: {state.bankroll_usd} vs {expected.get('bankroll_usd')}")
                
                if abs(state.daily_pnl_usd - expected.get("daily_pnl_usd", state.daily_pnl_usd)) > 0.01:
                    passed = False
                    failures.append(f"daily_pnl: {state.daily_pnl_usd} vs {expected.get('daily_pnl_usd')}")
                
                if state.open_position_count != expected.get("open_position_count", state.open_position_count):
                    passed = False
                    failures.append(f"positions: {state.open_position_count} vs {expected.get('open_position_count')}")
                
                if state.cooldown_active != expected.get("cooldown_active", state.cooldown_active):
                    passed = False
                    failures.append(f"cooldown: {state.cooldown_active} vs {expected.get('cooldown_active')}")
                
                # Check exposure_by_token
                expected_exposure = expected.get("exposure_by_token", {})
                for token, exp_amount in expected_exposure.items():
                    actual = state.exposure_by_token.get(token, 0)
                    if abs(actual - exp_amount) > 0.01:
                        passed = False
                        failures.append(f"token_exposure[{token}]: {actual} vs {exp_amount}")
                
                # Check entry_blocked
                if expected.get("entry_blocked", False) != entry_blocked:
                    passed = False
                    failures.append(f"entry_blocked: {entry_blocked} vs {expected.get('entry_blocked')}")
                
                # Report result
                if passed:
                    print(f"[state_smoke] Testing {case_id}... PASS", file=sys.stderr)
                    passed_count += 1
                else:
                    print(f"[state_smoke] Testing {case_id}... FAIL: {', '.join(failures)}", file=sys.stderr)
                    all_passed = False
    
    except FileNotFoundError:
        print(f"[state_smoke] ERROR: Fixture file not found at {fixture_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[state_smoke] ERROR: Invalid JSON in fixture: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[state_smoke] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    
    # Final result
    if all_passed:
        print(f"[state_smoke] OK ({passed_count}/{test_count} tests passed)", file=sys.stderr)
        sys.exit(0)
    else:
        print(f"[state_smoke] FAILED ({passed_count}/{test_count} tests passed)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_state_smoke_tests()
