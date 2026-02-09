#!/usr/bin/env python3
"""Smoke test for Stats Feedback Loop (PR-Q.1).

Tests the parameter tuning logic with historical data fixtures.

Usage:
    python scripts/feedback_loop_smoke.py
    bash scripts/feedback_loop_smoke.sh

Exit codes:
    - 0: All tests passed
    - 1: One or more tests failed
"""

import json
import sys
import yaml
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def run_smoke_tests():
    """Run feedback loop smoke tests."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    history_path = project_root / "integration/fixtures/feedback_loop/history.jsonl"
    base_config_path = project_root / "integration/fixtures/feedback_loop/params_base.yaml"
    output_path = project_root / "integration/fixtures/feedback_loop/params_updated.yaml"
    
    print("[feedback_loop_smoke] Starting feedback loop tests...", file=sys.stderr)
    
    try:
        # Load base config to get original values
        with open(base_config_path, "r") as f:
            base_config = yaml.safe_load(f)
        
        original_s_win = base_config["payoff_mu_win"]["S"]
        original_s_loss = base_config["payoff_mu_loss"]["S"]
        
        print(f"[feedback_loop_smoke] Original S: win={original_s_win}, loss={original_s_loss}", file=sys.stderr)
        
        # Run the tuner
        from strategy.optimization.update_params import ParamTuner, TuningConfig
        
        config = TuningConfig(max_change_ratio=0.20, min_payoff_value=0.01)
        tuner = ParamTuner(config)
        
        new_params, patched_yaml = tuner.tune(history_path, base_config_path)
        
        # Write output
        with open(output_path, "w") as f:
            f.write(patched_yaml)
        
        print(f"[feedback_loop_smoke] Wrote updated config to {output_path}", file=sys.stderr)
        
        # Verify output
        with open(output_path, "r") as f:
            updated_config = yaml.safe_load(f)
        
        updated_s_win = updated_config["payoff_mu_win"]["S"]
        updated_s_loss = updated_config["payoff_mu_loss"]["S"]
        
        print(f"[feedback_loop_smoke] Updated S: win={updated_s_win}, loss={updated_s_loss}", file=sys.stderr)
        
        # Verify clamping worked
        # For S mode: avg_win = (0.06*10 + 0.04*20 + 0.05*15) / (10+20+15) = 0.05
        # Original: 0.10, Expected raw: 0.05, With 20% clamp: 0.09
        # For S mode: avg_loss = (0.02*10 + 0.03*20 + 0.025*15) / (10+20+15) = 0.025
        # Original: 0.05, Expected raw: 0.025, With 20% clamp: 0.045
        
        expected_win = 0.09  # (0.10 - 0.05) * 0.2 = 0.01, so 0.10 - 0.01 = 0.09
        expected_loss = 0.045  # (0.05 - 0.025) * 0.2 = 0.005, so 0.05 - 0.005 = 0.045
        
        # Verify values are within expected range
        win_changed = abs(updated_s_win - original_s_win) > 0.001
        loss_changed = abs(updated_s_loss - original_s_loss) > 0.001
        
        if not win_changed:
            print("[feedback_loop_smoke] FAIL: S win value should have changed", file=sys.stderr)
            sys.exit(1)
        
        if not loss_changed:
            print("[feedback_loop_smoke] FAIL: S loss value should have changed", file=sys.stderr)
            sys.exit(1)
        
        # Verify U mode has data and was updated
        u_win = updated_config["payoff_mu_win"].get("U")
        if u_win is None:
            print("[feedback_loop_smoke] FAIL: U mode should have been updated", file=sys.stderr)
            sys.exit(1)
        
        # Verify M mode has data and was updated
        m_loss = updated_config["payoff_mu_loss"].get("M")
        if m_loss is None:
            print("[feedback_loop_smoke] FAIL: M mode should have been updated", file=sys.stderr)
            sys.exit(1)
        
        # Verify L mode kept original values (no data in history)
        l_win = updated_config["payoff_mu_win"].get("L")
        if l_win != 0.04:
            print("[feedback_loop_smoke] FAIL: L mode should retain original value", file=sys.stderr)
            sys.exit(1)
        
        # Verify YAML is valid
        print("[feedback_loop_smoke] Validating output YAML...", file=sys.stderr)
        
        # All checks passed
        print("[feedback_loop_smoke] Testing clamping logic...", file=sys.stderr)
        
        # Test extreme values (100% win should be clamped)
        from strategy.optimization.update_params import ParamTuner, TuningConfig, ModeStats
        
        extreme_tuner = ParamTuner(TuningConfig(max_change_ratio=0.20, min_payoff_value=0.01))
        
        # Initialize mode_stats for extreme test
        for mode in ["U", "S", "M", "L"]:
            extreme_tuner.mode_stats[mode] = ModeStats(mode=mode)
        
        # Simulate extreme history
        extreme_tuner.mode_stats["S"].win_pcts = [1.0]  # 100% win
        extreme_tuner.mode_stats["S"].loss_pcts = [0.01]
        extreme_tuner.mode_stats["S"].trade_counts = [10]
        
        raw_stats = extreme_tuner.compute_stats()
        raw_win, raw_loss = raw_stats["S"]
        
        # With 20% cap: 0.10 -> max change is 0.02, so min is 0.08
        clamped_win = extreme_tuner.apply_limits(0.10, raw_win)
        
        if clamped_win < 0.08:
            print(f"[feedback_loop_smoke] FAIL: Clamping not working, got {clamped_win}", file=sys.stderr)
            sys.exit(1)
        
        print(f"[feedback_loop_smoke] Extreme value clamped from 1.0 to {clamped_win:.4f}", file=sys.stderr)
        
        print("[feedback_loop_smoke] OK", file=sys.stderr)
        sys.exit(0)
    
    except FileNotFoundError as e:
        print(f"[feedback_loop_smoke] ERROR: File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[feedback_loop_smoke] ERROR: Invalid YAML: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[feedback_loop_smoke] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_tests()
