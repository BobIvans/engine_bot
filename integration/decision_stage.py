"""integration/decision_stage.py

Glue-stage for embedding unified decision logic into the pipeline.

Reads event stream (Candidates), loads wallet/token/polymarket data,
calls CopyScalpStrategy.decide_on_wallet_buy(), and:
- If Signal.decision == 'ENTER': passes to next stage
- If Signal.decision == 'SKIP': writes to reject-log

PR-PM.5: Risk Regime Integration
- Loads risk_regime from regime_timeline.parquet
- Applies multiplicative correction to edge: edge_final = edge_raw * (1 + alpha * risk_regime)
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from strategy.logic import (
    CopyScalpStrategy,
    WalletProfile,
    TokenSnapshot,
    PolymarketSnapshot,
    StrategyParams,
    Signal,
    Decision,
    Mode
)
from integration.parquet_io import ParquetReadConfig, iter_parquet_records


# Default paths
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "integration/fixtures/config"
DEFAULT_DECISION_DIR = PROJECT_ROOT / "integration/fixtures/decision"
DEFAULT_REGIME_TIMELINE_PATH = PROJECT_ROOT / "regime_timeline.parquet"


class DecisionStage:
    """
    Integration stage for unified decision logic.
    
    Loads configuration and fixtures, processes events through
    CopyScalpStrategy, and outputs signals or rejects.
    
    PR-PM.5: Supports risk regime adjustment via regime_timeline.parquet
    """
    
    def __init__(
        self,
        config_dir: Optional[str] = None,
        decision_dir: Optional[str] = None,
        params: Optional[StrategyParams] = None,
        regime_timeline_path: Optional[str] = None,
        skip_regime_adjustment: bool = False
    ):
        """
        Initialize stage with paths and strategy params.
        
        Args:
            config_dir: Path to config directory
            decision_dir: Path to decision fixtures directory
            params: Strategy parameters
            regime_timeline_path: Path to regime_timeline.parquet file
            skip_regime_adjustment: If True, skip regime adjustment
        """
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.decision_dir = Path(decision_dir) if decision_dir else DEFAULT_DECISION_DIR
        self.strategy = CopyScalpStrategy(params)
        self.rejects: List[Dict] = []
        self.signals: List[Signal] = []
        
        # PR-PM.5: Risk regime configuration
        self.skip_regime_adjustment = skip_regime_adjustment
        self.regime_timeline_path = Path(regime_timeline_path) if regime_timeline_path else DEFAULT_REGIME_TIMELINE_PATH
        self._cached_risk_regime: Optional[float] = None
        self._regime_cache_loaded = False
    
    def load_risk_regime(self, current_ts: Optional[int] = None) -> float:
        """
        Load the most recent risk_regime from regime_timeline.parquet.
        
        Selects the record with max ts <= current_ts.
        
        Args:
            current_ts: Current timestamp in milliseconds. If None, uses latest.
            
        Returns:
            risk_regime value in [-1.0, +1.0], or 0.0 if file missing/empty.
        """
        # Return cached value if already loaded
        if self._regime_cache_loaded:
            return self._cached_risk_regime if self._cached_risk_regime is not None else 0.0
        
        self._regime_cache_loaded = True
        
        # Check if file exists
        if not self.regime_timeline_path.exists():
            print(f"[decision] regime_timeline not found at {self.regime_timeline_path}, using neutral regime", file=sys.stderr)
            # Fallback: if regime timeline missing, use bullish_score from scenario event (if present)
            try:
                bull = (event or {}).get('bullish_score')
                if bull is not None:
                    risk_regime = float(bull)
            except Exception:
                pass
            self._cached_risk_regime = 0.0
            return 0.0
        
        try:
            cfg = ParquetReadConfig(
                path=str(self.regime_timeline_path),
                limit=None
            )
            
            # Find record with max ts <= current_ts
            max_ts = -1
            selected_record: Optional[Dict] = None
            
            for record in iter_parquet_records(cfg):
                ts = record.get("ts", 0)
                if ts is None:
                    continue
                
                # If current_ts is provided, only consider records <= current_ts
                if current_ts is not None:
                    if ts <= current_ts and ts > max_ts:
                        max_ts = ts
                        selected_record = record
                else:
                    # No timestamp filter, just take the last one
                    if ts > max_ts:
                        max_ts = ts
                        selected_record = record
            
            if selected_record is None:
                print("[decision] regime_timeline is empty, using neutral regime", file=sys.stderr)
                self._cached_risk_regime = 0.0
                return 0.0
            
            risk_regime = selected_record.get("risk_regime", 0.0)
            if risk_regime is None:
                risk_regime = 0.0
            
            # Validate bounds
            if not (-1.001 <= risk_regime <= 1.001):
                print(f"[decision] WARNING: risk_regime={risk_regime} out of bounds, clipping to 0.0", file=sys.stderr)
                risk_regime = 0.0
            
            self._cached_risk_regime = risk_regime
            return risk_regime
            
        except Exception as e:
            print(f"[decision] ERROR loading regime_timeline: {e}, using neutral regime", file=sys.stderr)
            self._cached_risk_regime = 0.0
            return 0.0
    
    def load_wallet_profile(self, wallet_address: str) -> Optional[WalletProfile]:
        """Load wallet profile from fixtures or return None."""
        profiles_dir = self.decision_dir / "wallets"
        profile_file = profiles_dir / f"{wallet_address}.json"
        
        if profile_file.exists():
            with open(profile_file, 'r') as f:
                data = json.load(f)
                return WalletProfile(**data)
        return None
    
    def load_token_snapshot(self, token_address: str) -> Optional[TokenSnapshot]:
        """Load token snapshot from fixtures or return None."""
        tokens_dir = self.decision_dir / "tokens"
        token_file = tokens_dir / f"{token_address}.json"
        
        if token_file.exists():
            with open(token_file, 'r') as f:
                data = json.load(f)
                return TokenSnapshot(**data)
        return None
    
    def load_polymarket_snapshot(self, event_id: str) -> Optional[PolymarketSnapshot]:
        """Load polymarket snapshot from fixtures or return None."""
        polymarket_dir = self.decision_dir / "polymarket"
        event_file = polymarket_dir / f"{event_id}.json"
        
        if event_file.exists():
            with open(event_file, 'r') as f:
                data = json.load(f)
                return PolymarketSnapshot(**data)
        return None
    
    def process_event(
        self,
        event: Dict,
        portfolio_value: float,
        timestamp: Optional[datetime] = None
    ) -> Signal:
        """
        Process a single event through decision logic.
        
        Args:
            event: Event dict with keys wallet_address, token_address, [event_id]
            portfolio_value: Current portfolio value
            timestamp: Current time
            
        Returns:
            Signal with decision
        """
        wallet_address = event.get("wallet_address")
        token_address = event.get("token_address")
        event_id = event.get("event_id")
        
        # Load enriched data
        wallet = self.load_wallet_profile(wallet_address)
        token = self.load_token_snapshot(token_address)
        polymarket = self.load_polymarket_snapshot(event_id) if event_id else None
        
        # If fixtures not available, create from event data
        if wallet is None:
            wallet = WalletProfile(
                wallet_address=wallet_address,
                winrate=event.get("winrate", 0.5),
                roi_mean=event.get("roi_mean", 0.0),
                trade_count=event.get("trade_count", 10),
                pnl_ratio=event.get("pnl_ratio", 1.0),
                avg_holding_time_sec=event.get("avg_holding_time_sec", 300),
                smart_money_score=event.get("smart_money_score", 0.5)
            )
        
        if token is None:
            token = TokenSnapshot(
                token_address=token_address,
                symbol=event.get("symbol", "UNKNOWN"),
                liquidity_usd=event.get("liquidity_usd", 50000),
                volume_24h=event.get("volume_24h", 25000),
                price=event.get("price", 1.0),
                holder_count=event.get("holder_count", 500),
                is_honeypot=event.get("is_honeypot", False),
                buy_tax_bps=event.get("buy_tax_bps", 0),
                sell_tax_bps=event.get("sell_tax_bps", 0),
                is_freezable=event.get("is_freezable", False)
            )
        
        if polymarket is None and event_id:
            polymarket = PolymarketSnapshot(
                event_id=event_id,
                event_title=event.get("event_title", "Unknown"),
                outcome=event.get("outcome", "Unknown"),
                probability=event.get("probability", 0.5),
                volume_usd=event.get("polymarket_volume_usd", 0),
                liquidity_usd=event.get("polymarket_liquidity_usd", 0),
                bullish_score=event.get("bullish_score", 0.5)
            )
        
        # PR-PM.5: Load risk_regime from timeline
        risk_regime = self.load_risk_regime()
        
        # Make decision with regime integration
        signal = self.strategy.decide_on_wallet_buy(
            wallet=wallet,
            token=token,
            polymarket=polymarket,
            portfolio_value=portfolio_value,
            timestamp=timestamp,
            risk_regime=risk_regime,
            skip_regime_adjustment=self.skip_regime_adjustment
        )
        
        # PR-PM.5: Log regime application for ENTER signals
        if signal.decision == Decision.ENTER and signal.edge_raw is not None and signal.edge_final is not None:
            if self.skip_regime_adjustment:
                print(f"[decision] skip_regime_adjustment=True → edge {signal.edge_raw:.3f} (no adjustment)", file=sys.stderr)
            else:
                print(f"[decision] applied risk_regime={risk_regime:+.2f} (alpha={self.strategy.params.regime_alpha:.2f}) → edge {signal.edge_raw:.3f} → {signal.edge_final:.3f}", file=sys.stderr)
        
        # Record reject if SKIP
        if signal.decision == Decision.SKIP:
            self.rejects.append({
                "timestamp": datetime.utcnow().isoformat() if timestamp is None else timestamp.isoformat(),
                "wallet_address": wallet_address,
                "token_address": token_address,
                "reason": signal.reason,
                "regime": signal.regime,
                "ev_score": signal.ev_score,
                "metadata": signal.metadata
            })
        else:
            self.signals.append(signal)
        
        return signal
    
    def process_scenarios(self, scenarios_file: str) -> Dict[str, Signal]:
        """
        Process scenarios from JSONL file.
        
        Returns:
            Dict mapping scenario_id to Signal
        """
        results = {}
        
        with open(scenarios_file, 'r') as f:
            for line in f:
                if line.strip():
                    scenario = json.loads(line)
                    scenario_id = scenario.get("id", "unknown")
                    
                    signal = self.process_event(
                        event=scenario["event"],
                        portfolio_value=scenario.get("portfolio_value", 10000.0),
                        timestamp=datetime.utcnow()
                    )
                    
                    results[scenario_id] = signal
        
        return results
    
    def get_rejects(self) -> List[Dict]:
        """Get recorded rejects."""
        return self.rejects
    
    def get_signals(self) -> List[Signal]:
        """Get recorded signals."""
        return self.signals


def run_stage(
    scenarios_file: str = None,
    config_dir: str = None,
    output_dir: str = None,
    # PR-PM.5: Risk regime integration parameters
    regime_timeline_path: str = None,
    skip_regime_adjustment: bool = False
) -> Dict[str, Any]:
    """
    Run decision stage with given scenarios.
    
    Args:
        scenarios_file: Path to scenarios JSONL file
        config_dir: Path to config directory
        output_dir: Path to output directory
        regime_timeline_path: Path to regime_timeline.parquet file
        skip_regime_adjustment: If True, skip regime adjustment
        
    Returns:
        Dict with results summary
    """
    stage = DecisionStage(
        config_dir=config_dir,
        regime_timeline_path=regime_timeline_path,
        skip_regime_adjustment=skip_regime_adjustment
    )
    
    if scenarios_file is None:
        scenarios_file = str(stage.decision_dir / "scenarios.jsonl")
    
    if not Path(scenarios_file).exists():
        return {"error": f"Scenarios file not found: {scenarios_file}"}
    
    results = stage.process_scenarios(scenarios_file)
    
    # Prepare output
    output = {
        "processed": len(results),
        "signals": len(stage.get_signals()),
        "rejects": len(stage.get_rejects()),
        "scenarios": {}
    }
    
    for scenario_id, signal in results.items():
        output["scenarios"][scenario_id] = {
            "decision": signal.decision.value,
            "reason": signal.reason,
            "mode": signal.mode.value if signal.mode else None,
            "size_pct": signal.size_pct,
            "ev_score": signal.ev_score,
            "regime": signal.regime
        }
    
    # Write rejects to file if output_dir specified
    if output_dir:
        output_path = Path(output_dir) / "rejects.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            for reject in stage.get_rejects():
                f.write(json.dumps(reject) + "\n")
        
        output["rejects_file"] = str(output_path)
    
    return output


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run decision stage")
    parser.add_argument("--scenarios", help="Path to scenarios JSONL file")
    parser.add_argument("--config", help="Path to config directory")
    parser.add_argument("--output", help="Path to output directory")
    args = parser.parse_args()
    
    result = run_stage(
        scenarios_file=args.scenarios,
        config_dir=args.config,
        output_dir=args.output
    )
    
    print(json.dumps(result, indent=2, default=str))
