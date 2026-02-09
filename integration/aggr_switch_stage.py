"""integration/aggr_switch_stage.py

Glue-stage for testing aggressive switch logic on price update stream.

Receives "Position Updates" stream, calls maybe_switch_to_aggressive(),
and logs results: SWITCH_TRIGGERED or IGNORED.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.aggr_logic import (
    maybe_switch_to_aggressive,
    passes_aggressive_safety,
    PositionSnapshot,
    WalletProfile,
    TokenSnapshot,
    PortfolioState,
    AggressiveSwitchParams
)


# Default paths
DEFAULT_FIXTURES_DIR = PROJECT_ROOT / "integration/fixtures/aggr_switch"


class AggrSwitchStage:
    """
    Integration stage for aggressive switch logic.
    
    Processes position updates through aggressive switch logic
    and emits results.
    """
    
    def __init__(
        self,
        fixtures_dir: Optional[str] = None,
        params: Optional[AggressiveSwitchParams] = None
    ):
        """Initialize stage with paths and params."""
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else DEFAULT_FIXTURES_DIR
        self.params = params or AggressiveSwitchParams()
        self.results: List[Dict] = []
    
    def load_wallet(self, wallet_address: str) -> Optional[WalletProfile]:
        """Load wallet profile from fixtures."""
        wallets_dir = self.fixtures_dir / "wallets"
        wallet_file = wallets_dir / f"{wallet_address}.json"
        
        if wallet_file.exists():
            with open(wallet_file, 'r') as f:
                data = json.load(f)
                return WalletProfile(**data)
        return None
    
    def load_token(self, token_address: str) -> Optional[TokenSnapshot]:
        """Load token snapshot from fixtures."""
        tokens_dir = self.fixtures_dir / "tokens"
        token_file = tokens_dir / f"{token_address}.json"
        
        if token_file.exists():
            with open(token_file, 'r') as f:
                data = json.load(f)
                return TokenSnapshot(**data)
        return None
    
    def process_position_update(
        self,
        position_data: Dict,
        wallet_data: Dict,
        token_data: Dict,
        portfolio_data: Dict
    ) -> Dict:
        """
        Process a single position update.
        
        Returns:
            Dict with decision result
        """
        # Build snapshots from dict data
        position = PositionSnapshot(
            position_id=position_data.get("position_id", "unknown"),
            token_address=position_data["token_address"],
            wallet_address=position_data["wallet_address"],
            base_mode=position_data["base_mode"],
            entry_price=position_data["entry_price"],
            current_price=position_data["current_price"],
            position_size=position_data["position_size"],
            entry_time_sec=position_data["entry_time_sec"],
            current_roi=position_data["current_roi"]
        )
        
        wallet = WalletProfile(
            wallet_address=wallet_data["wallet_address"],
            winrate=wallet_data["winrate"],
            roi_mean=wallet_data["roi_mean"],
            trade_count=wallet_data["trade_count"],
            smart_money_score=wallet_data.get("smart_money_score", 0.5)
        )
        
        token = TokenSnapshot(
            token_address=token_data["token_address"],
            symbol=token_data["symbol"],
            liquidity_usd=token_data["liquidity_usd"],
            spread_bps=token_data.get("spread_bps", 50)
        )
        
        portfolio = PortfolioState(
            total_value_usd=portfolio_data["total_value_usd"],
            aggr_positions_count=portfolio_data.get("aggr_positions_count", 0),
            aggr_exposure_usd=portfolio_data.get("aggr_exposure_usd", 0.0),
            daily_aggr_count=portfolio_data.get("daily_aggr_count", 0)
        )
        
        # Make decision
        new_mode, reason = maybe_switch_to_aggressive(
            position, wallet, token, portfolio, self.params
        )
        
        result = {
            "position_id": position.position_id,
            "base_mode": position.base_mode,
            "entry_time_sec": position.entry_time_sec,
            "current_roi": position.current_roi,
            "new_mode": new_mode,
            "reason": reason,
            "triggered": new_mode is not None
        }
        
        self.results.append(result)
        return result
    
    def process_scenarios(self, scenarios_file: str) -> Dict[str, Dict]:
        """
        Process scenarios from JSONL file.
        
        Returns:
            Dict mapping scenario_id to result
        """
        results = {}
        
        with open(scenarios_file, 'r') as f:
            for line in f:
                if line.strip():
                    scenario = json.loads(line)
                    scenario_id = scenario.get("id", "unknown")
                    
                    result = self.process_position_update(
                        position_data=scenario["position"],
                        wallet_data=scenario["wallet"],
                        token_data=scenario["token"],
                        portfolio_data=scenario.get("portfolio", {
                            "total_value_usd": 10000.0,
                            "aggr_positions_count": 0,
                            "aggr_exposure_usd": 0.0,
                            "daily_aggr_count": 0
                        })
                    )
                    
                    result["expected_decision"] = scenario.get("expected_decision")
                    result["expected_reason"] = scenario.get("expected_reason")
                    results[scenario_id] = result
        
        return results
    
    def get_results(self) -> List[Dict]:
        """Get all processed results."""
        return self.results


def run_stage(
    scenarios_file: str = None,
    fixtures_dir: str = None,
    output_json: bool = False
) -> Dict[str, Any]:
    """
    Run aggressive switch stage with scenarios.
    
    Returns:
        Dict with results summary
    """
    stage = AggrSwitchStage(fixtures_dir=fixtures_dir)
    
    if scenarios_file is None:
        scenarios_file = str(stage.fixtures_dir / "scenarios.jsonl")
    
    if not Path(scenarios_file).exists():
        return {"error": f"Scenarios file not found: {scenarios_file}"}
    
    results = stage.process_scenarios(scenarios_file)
    
    # Count triggered vs ignored
    triggered = sum(1 for r in results.values() if r["triggered"])
    ignored = len(results) - triggered
    
    output = {
        "processed": len(results),
        "triggered": triggered,
        "ignored": ignored,
        "scenarios": {}
    }
    
    for scenario_id, result in results.items():
        output["scenarios"][scenario_id] = {
            "new_mode": result["new_mode"],
            "reason": result["reason"],
            "triggered": result["triggered"],
            "expected_decision": result.get("expected_decision"),
            "expected_reason": result.get("expected_reason"),
            "match": (
                result["new_mode"] == result.get("expected_decision") and
                result["reason"] == result.get("expected_reason")
            )
        }
    
    if output_json:
        print(json.dumps(output, indent=2))
    
    return output


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run aggressive switch stage")
    parser.add_argument("--scenarios", help="Path to scenarios JSONL file")
    parser.add_argument("--fixtures", help="Path to fixtures directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    result = run_stage(
        scenarios_file=args.scenarios,
        fixtures_dir=args.fixtures,
        output_json=args.json
    )
    
    if not args.json:
        print(json.dumps(result, indent=2, default=str))
