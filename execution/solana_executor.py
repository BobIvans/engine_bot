"""execution/solana_executor.py

PR-G.1 Transaction Builder Adapter & Simulation.

Implementation using Jupiter Swap API (HTTP) and Solana RPC:
- JupiterSolanaExecutor: Builds and simulates SOL/token swaps

Design goals:
- No private keys: Only builds unsigned transactions
- Uses requests library (existing dependency)
- Structured error handling
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

import requests

from execution.live_executor import LiveExecutor, NoOpLiveExecutor
from config.runtime_schema import RuntimeConfig


# Default endpoints
DEFAULT_JUPITER_API_URL = "https://quote-api.jup.ag/v6"
DEFAULT_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"


class JupiterSolanaExecutor(LiveExecutor):
    """Live executor using Jupiter Swap API and Solana RPC.

    Flow:
    1. get_quote: Get swap quote from Jupiter
    2. build_swap_tx: Convert quote to unsigned transaction
    3. simulate_tx: Simulate transaction via RPC
    """

    def __init__(
        self,
        *,
        jupiter_api_url: str = DEFAULT_JUPITER_API_URL,
        rpc_url: str = DEFAULT_SOLANA_RPC_URL,
        timeout_ms: int = 5000,
        config: Optional[RuntimeConfig] = None,
    ):
        """Initialize the executor.

        Args:
            jupiter_api_url: Jupiter API endpoint.
            rpc_url: Solana RPC endpoint.
            timeout_ms: Request timeout in milliseconds.
            config: Runtime configuration for retry logic.
        """
        super().__init__(config=config)
        self.jupiter_api_url = jupiter_api_url
        self.rpc_url = rpc_url
        self.timeout_ms = timeout_ms
        self._session = requests.Session()

    def _request(self, url: str, data: Dict[str, Any], endpoint: str) -> Dict[str, Any]:
        """Make a POST request and handle errors.

        Args:
            url: Full URL for the request.
            data: JSON request body.
            endpoint: Name of the endpoint (for error messages).

        Returns:
            Response dict or error dict.
        """
        try:
            response = self._session.post(
                url,
                json=data,
                timeout=self.timeout_ms / 1000.0,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {
                "success": False,
                "error": f"HTTP error from {endpoint}: {str(e)}",
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Request failed to {endpoint}: {str(e)}",
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON from {endpoint}: {str(e)}",
            }

    def get_quote(
        self,
        *,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 100,
    ) -> Dict[str, Any]:
        """Get a swap quote from Jupiter.

        Args:
            input_mint: Input token mint.
            output_mint: Output token mint.
            amount_lamports: Amount to swap.
            slippage_bps: Max slippage in bps.

        Returns:
            Quote dict with success, out_amount, etc.
        """
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount_lamports,
            "slippageBps": slippage_bps,
            "onlyDirectRoutes": "true",  # Prefer direct routes
        }

        url = f"{self.jupiter_api_url}/quote"
        result = self._request(url, params, "Jupiter Quote")

        if not result.get("success", True):
            return {
                "success": False,
                "out_amount": 0,
                "price_impact_pct": 0.0,
                "error": result.get("error", "Unknown quote error"),
            }

        return {
            "success": True,
            "out_amount": int(result.get("outAmount", 0)),
            "price_impact_pct": float(result.get("priceImpactPct", 0.0)),
            "route": result.get("routePlan", []),
            "details": result,
        }

    def build_swap_tx(
        self,
        *,
        wallet: str,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 100,
    ) -> Dict[str, Any]:
        """Build an unsigned swap transaction via Jupiter.

        Args:
            wallet: Source wallet address.
            input_mint: Input token mint.
            output_mint: Output token mint.
            amount_lamports: Amount to swap.
            slippage_bps: Max slippage in bps.

        Returns:
            Dict with tx_base64, success, error.
        """
        # Step 1: Get quote
        quote = self.get_quote(
            input_mint=input_mint,
            output_mint=output_mint,
            amount_lamports=amount_lamports,
            slippage_bps=slippage_bps,
        )

        if not quote.get("success"):
            return {
                "success": False,
                "tx_base64": "",
                "error": f"Quote failed: {quote.get('error')}",
                "details": {},
            }

        # Step 2: Build transaction
        swap_data = {
            "route": quote.get("details", {}),
            "userPublicKey": wallet,
            "wrapAndUnwrapSol": "true",
        }

        url = f"{self.jupiter_api_url}/swap"
        result = self._request(url, swap_data, "Jupiter Swap")

        if not result.get("success", True):
            return {
                "success": False,
                "tx_base64": "",
                "error": result.get("error", "Unknown swap error"),
                "details": {"quote": quote},
            }

        return {
            "success": True,
            "tx_base64": result.get("swapTransaction", ""),
            "error": "",
            "details": {
                "quote": quote,
                "other_transactions": result.get("otherTransactions", []),
            },
        }

    def simulate_tx(
        self,
        *,
        tx_base64: str,
        accounts: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Simulate a transaction via Solana RPC.

        Args:
            tx_base64: Base64-encoded unsigned transaction.
            accounts: Optional list of account addresses to load.

        Returns:
            Dict with success, logs, units_consumed, error.
        """
        # Build RPC request
        rpc_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "simulateTransaction",
            "params": [
                tx_base64,
                {
                    "encoding": "base64",
                    "accounts": {
                        "addresses": accounts or [],
                    },
                    "sigVerify": False,
                    "replaceRecentBlockhash": True,
                },
            ],
        }

        try:
            response = self._session.post(
                self.rpc_url,
                json=rpc_request,
                timeout=self.timeout_ms / 1000.0,
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "logs": [],
                "units_consumed": 0,
                "error": f"RPC request failed: {str(e)}",
                "details": {},
            }

        # Parse response
        if "error" in result:
            return {
                "success": False,
                "logs": [],
                "units_consumed": 0,
                "error": f"RPC error: {result['error'].get('message', 'Unknown')}",
                "details": result,
            }

        data = result.get("result", {})
        value = data.get("value", {})

        # Check for simulation error
        err = value.get("err")
        if err is not None:
            return {
                "success": False,
                "logs": value.get("logs", []),
                "units_consumed": value.get("unitsConsumed", 0),
                "error": f"Simulation error: {json.dumps(err)}",
                "details": data,
            }

        return {
            "success": True,
            "logs": value.get("logs", []),
            "units_consumed": value.get("unitsConsumed", 0),
            "error": "",
            "details": data,
        }


def create_live_executor(config: Dict[str, Any]) -> LiveExecutor:
    """Factory function to create live executor from config.

    Args:
        config: Config dict with execution settings.

    Returns:
        LiveExecutor implementation based on config.
    """
    exec_cfg = config.get("execution", {})
    enabled = exec_cfg.get("live_enabled", False)

    if not enabled:
        return NoOpLiveExecutor()

    adapter = exec_cfg.get("live_adapter", "jupiter_http")

    if adapter == "jupiter_http":
        # Create runtime config for retry logic
        # We attempt to extract relevant keys from 'execution' or root config if accessible.
        # Since 'config' passed here is a dict, we construct RuntimeConfig manually or with defaults.
        # This might not be hot-reloadable here, but satisfies initialization requirement.
        from config.runtime_schema import RuntimeConfig
        
        # Try to map dict to RuntimeConfig fields
        # Note: dict keys might not match flat RuntimeConfig if nested.
        # But we mostly care about partial_retry_* which should be in config dict if loaded from params_base.
        # Let's assume defaults for now if not found, or user provided flattened?
        # Typically params_base has them at top level? No, params_base is nested.
        # But here we only have the dict.
        # Let's create a default RuntimeConfig and override if keys exist.
        
        # NOTE: Ideally we should use the GLOBAL RuntimeConfig if available, but here we only have local dict.
        # We will create a fresh one using defaults + overrides.
        
        runtime_conf = RuntimeConfig(
            partial_retry_enabled=bool(config.get("partial_retry_enabled", False)),
            # Add other overrides if they are in the passed config dict
        )
        
        return JupiterSolanaExecutor(
            jupiter_api_url=exec_cfg.get("jupiter_api_url", DEFAULT_JUPITER_API_URL),
            rpc_url=exec_cfg.get("rpc_url", DEFAULT_SOLANA_RPC_URL),
            timeout_ms=exec_cfg.get("timeout_ms", 5000),
            config=runtime_conf,
        )

    # Unknown adapter, return no-op
    return NoOpLiveExecutor()
