"""
Bitquery GraphQL Adapter.

Fetches wallet trade history from Bitquery Solana GraphQL API.
Acts as a fallback source for complex data not available in standard providers.
"""

import sys
import json
import time
import os
from typing import List, Dict, Any, Optional, Iterator, Tuple
from datetime import datetime

from ingestion.sources.base import TradeSource
from strategy.ingestion import normalize_bitquery_trade, TradeEvent


class BitquerySource(TradeSource):
    """
    Adapter for Bitquery Solana GraphQL API.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("BITQUERY_API_KEY")
        self.endpoint = "https://graphql.bitquery.io"
        self.credits_remaining = None
        
    def supports_complex_aggregations(self) -> bool:
        return True
        
    def _build_query(self, wallets: List[str], from_ts: int, to_ts: int) -> str:
        """Construct GraphQL query for wallet trades."""
        # Convert timestamps to ISO8601 if needed, but Bitquery often accepts various formats.
        # For this implementation, we'll assume we select using timestamp blocks
        # or simplified criteria suitable for the API version.
        
        # Simplified query structure for demonstration/MVP
        # In reality, this would be a complex V2/V3 query
        wallets_str = json.dumps(wallets)
        
        return f"""
        {{
          solana {{
            dexTrades(
              options: {{limit: 100}}
              date: {{since: "{datetime.fromtimestamp(from_ts).isoformat()}", till: "{datetime.fromtimestamp(to_ts).isoformat()}"}}
              any: [
                {{trade: {{side: {{is: BUY}}}}}},
                {{trade: {{side: {{is: SELL}}}}}}
              ]
              makerAddress: {{in: {wallets_str}}}
            ) {{
              block {{
                timestamp {{
                  unixtime
                }}
              }}
              transaction {{
                signature
              }}
              swaps: tradeIndex {{
                amountIn
                amountOut
                dex {{
                  programId
                }}
                account {{
                  owner {{
                    address
                  }}
                }}
                tokenAccount {{
                  mint {{
                    address
                  }}
                }}
              }}
            }}
          }}
        }}
        """

    def fetch_graphql(self, query: str) -> Dict[str, Any]:
        """
        Execute GraphQL query. 
        MOCK implementation for purely offline/fixture-based environment requirement unless configured.
        In a real scenario, this would use requests.post().
        """
        # For this PR, actual network calls are not required/encouraged in test environment
        # We rely on the pipeline to inject fixture data if needed
        if not self.api_key:
            print("[bitquery] WARN: no API key, skipping fetch", file=sys.stderr)
            return {}
            
        # TODO: Implement actual requests.post logic if we were live
        # headers = {"X-API-KEY": self.api_key}
        # response = requests.post(self.endpoint, json={"query": query}, headers=headers)
        # ...
        return {}

    def fetch_wallet_trades(self, wallets: List[str], from_ts: int, to_ts: int) -> List[TradeEvent]:
        """
        Fetch trades for specific wallets in time range.
        
        Args:
            wallets: List of wallet addresses
            from_ts: Start timestamp (unix)
            to_ts: End timestamp (unix)
            
        Returns:
            List of normalized TradeEvents
        """
        if not self.api_key:
            # Check if we are running in a mode that allows mock data injection via other means
            # For now, just warn and return empty
            print("[bitquery] WARN: no API key provided", file=sys.stderr)
            return []
            
        query = self._build_query(wallets, from_ts, to_ts)
        # In real impl: data = self.fetch_graphql(query)
        # Here we return empty as pure fetch is stubbed for safety/cost
        return []

    def process_response(self, response_data: Dict[str, Any]) -> Tuple[List[TradeEvent], List[Tuple[Dict, str]]]:
        """
        Process a raw GraphQL response (from API or fixture).
        
        Returns:
            (valid_trades, rejected_items)
            rejected_items is list of (raw_node, reason)
        """
        valid_trades = []
        rejected = []
        
        try:
            trades_data = response_data.get("solana", {}).get("dexTrades", [])
        except AttributeError:
            return [], []
            
        if not trades_data:
            return [], []
            
        for node in trades_data:
            event, reject_reason = normalize_bitquery_trade(node)
            if event:
                valid_trades.append(event)
            else:
                rejected.append((node, reject_reason))
                
        return valid_trades, rejected

    def iter_records(self) -> Iterator[Dict[str, Any]]:
        """BaseSource interface implementation (unused for this specific fetcher pattern but required)."""
        return iter([])
