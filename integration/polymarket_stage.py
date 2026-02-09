"""integration/polymarket_stage.py

PR-F.5 Polymarket Ingestion & Normalization - Glue Stage

Fetches data from PolymarketSource, normalizes via sentiment.py,
and enriches the pipeline context with PolymarketSnapshot.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.sources.polymarket import PolymarketClient
from ingestion.sentiment import (
    normalize_polymarket_state,
    PolymarketSnapshot,
    PolymarketNormalizationParams
)


# Default paths
DEFAULT_FIXTURES_DIR = PROJECT_ROOT / "integration/fixtures/polymarket"


class PolymarketStage:
    """
    Integration stage for Polymarket data ingestion and normalization.

    Fetches market data, normalizes to PolymarketSnapshot,
    and enriches pipeline context.
    """

    def __init__(
        self,
        fixtures_dir: Optional[str] = None,
        normalization_params: Optional[PolymarketNormalizationParams] = None,
        client: Optional[PolymarketClient] = None
    ):
        """Initialize stage with paths and dependencies."""
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else DEFAULT_FIXTURES_DIR
        self.params = normalization_params or PolymarketNormalizationParams()
        self.client = client or PolymarketClient()
        self.last_snapshot: Optional[PolymarketSnapshot] = None

    def fetch_and_normalize(
        self,
        market_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        mock_data: Optional[List[Dict]] = None
    ) -> PolymarketSnapshot:
        """
        Fetch Polymarket data and normalize to snapshot.

        Args:
            market_ids: List of market IDs to fetch
            tags: Optional tags to filter markets
            mock_data: Optional mock data (overrides API calls)

        Returns:
            PolymarketSnapshot with normalized scores
        """
        if mock_data is not None:
            # Use provided mock data directly
            markets = mock_data
        elif market_ids:
            # Fetch specific markets
            markets = []
            for market_id in market_ids:
                data = self.client.fetch_market(market_id)
                if data:
                    markets.append(data)
        else:
            # Return neutral snapshot
            return self._neutral_snapshot()

        # Normalize
        snapshot = normalize_polymarket_state(markets, self.params)
        self.last_snapshot = snapshot

        return snapshot

    def _neutral_snapshot(self) -> PolymarketSnapshot:
        """Return neutral snapshot when no data available."""
        return PolymarketSnapshot(
            event_id="neutral",
            event_title="Neutral Market",
            outcome="Neutral",
            probability=0.5,
            volume_usd=0.0,
            liquidity_usd=0.0,
            bullish_score=0.5,
            event_risk=0.0,
            is_stale=True,
            data_quality="missing"
        )

    def run_from_fixtures(self, scenario_file: str = None) -> Dict[str, Any]:
        """
        Run stage using fixtures from JSONL file.

        Args:
            scenario_file: Path to scenarios JSONL file

        Returns:
            Dict with results
        """
        if scenario_file is None:
            scenario_file = str(self.fixtures_dir / "scenarios.jsonl")

        results = {}

        with open(scenario_file, 'r') as f:
            for line in f:
                if line.strip():
                    scenario = json.loads(line)
                    scenario_id = scenario.get("id", "unknown")

                    # Extract mock markets from scenario
                    mock_markets = scenario.get("markets", [])

                    # Normalize
                    snapshot = self.fetch_and_normalize(mock_data=mock_markets)

                    # Check assertions
                    expected_bullish = scenario.get("expected_bullish_score")
                    expected_risk = scenario.get("expected_event_risk")

                    passed = True
                    assertions = {}

                    if expected_bullish is not None:
                        assertions["bullish_score"] = {
                            "actual": snapshot.bullish_score,
                            "expected": expected_bullish,
                            "passed": abs(snapshot.bullish_score - expected_bullish) < 0.01
                        }
                        if not assertions["bullish_score"]["passed"]:
                            passed = False

                    if expected_risk is not None:
                        assertions["event_risk"] = {
                            "actual": snapshot.event_risk,
                            "expected": expected_risk,
                            "passed": abs(snapshot.event_risk - expected_risk) < 0.01
                        }
                        if not assertions["event_risk"]["passed"]:
                            passed = False

                    results[scenario_id] = {
                        "snapshot": {
                            "event_id": snapshot.event_id,
                            "bullish_score": snapshot.bullish_score,
                            "event_risk": snapshot.event_risk,
                            "data_quality": snapshot.data_quality
                        },
                        "assertions": assertions,
                        "passed": passed
                    }

        return results


def run_stage(
    scenario_file: str = None,
    fixtures_dir: str = None
) -> Dict[str, Any]:
    """
    Run Polymarket stage.

    Returns:
        Dict with results
    """
    stage = PolymarketStage(fixtures_dir=fixtures_dir)
    return stage.run_from_fixtures(scenario_file)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Polymarket ingestion stage")
    parser.add_argument("--scenarios", help="Path to scenarios JSONL file")
    parser.add_argument("--fixtures", help="Path to fixtures directory")
    args = parser.parse_args()

    result = run_stage(
        scenario_file=args.scenarios,
        fixtures_dir=args.fixtures
    )

    print(json.dumps(result, indent=2, default=str))
