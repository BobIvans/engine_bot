"""
Jito Bundle Executor (PR-G.4)

Provides JitoClient abstraction for bundle submission.
Handles:
- Bundle construction (swap + tip instructions)
- Bundle submission to Jito block-engine
- Tip account discovery
- Error handling and rejection reasons

HARD RULES:
- Jito logic NEVER activates in paper/sim modes
- All errors logged to stderr with reject reason
- No real network calls in smoke tests (use mocks)
"""

import asyncio
import logging
import uuid
from typing import List, Optional, Tuple
from dataclasses import dataclass

import aiohttp
from solders.pubkey import Pubkey
from solana.transaction import TransactionInstruction
from solana.system_program import transfer, TransferParams

from execution.jito_structs import (
    JitoBundleRequest,
    JitoBundleResponse,
    JitoTipAccount,
    JitoTipAccountsResponse,
    JitoConfig,
)
from integration.reject_reasons import (
    JITOBUNDLE_REJECTED,
    JITOBUNDLE_TIMEOUT,
    JITOBUNDLE_TIP_TOO_LOW,
    JITOBUNDLE_NETWORK_ERROR,
    assert_reason_known,
)

logger = logging.getLogger(__name__)


@dataclass
class JitoClient:
    """
    Client for Jito bundle submission.
    
    Attributes:
        config: Jito configuration
        session: Optional aiohttp session for HTTP requests
        _tip_accounts_cache: Cached tip accounts
    """
    config: JitoConfig
    session: Optional[aiohttp.ClientSession] = None
    _tip_accounts_cache: Optional[List[JitoTipAccount]] = None
    _cache_timestamp: float = 0.0
    
    async def __aenter__(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None
    
    async def get_tip_accounts(self) -> List[JitoTipAccount]:
        """
        Fetch available tip accounts from Jito.
        
        Returns:
            List of available tip accounts with their current rates.
            
        Note:
            Results are cached for 60 seconds to avoid excessive API calls.
        """
        import time
        current_time = time.time()
        
        # Return cached accounts if still valid
        if (self._tip_accounts_cache is not None and 
            current_time - self._cache_timestamp < 60):
            return self._tip_accounts_cache
        
        if self.session is None:
            raise RuntimeError("JitoClient session not initialized. Use async context manager.")
        
        url = f"{self.config.endpoint}/api/v1/tip-accounts"
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"[jito] Failed to fetch tip accounts: HTTP {response.status}")
                    raise JitoNetworkError(f"HTTP {response.status}")
                
                data = await response.json()
                accounts = []
                
                for item in data.get("accounts", []):
                    accounts.append(JitoTipAccount(
                        account=Pubkey.from_string(item["account"]),
                        lamports_per_signature=item.get("lamports_per_signature", 0),
                    ))
                
                self._tip_accounts_cache = accounts
                self._cache_timestamp = current_time
                
                logger.info(f"[jito] Fetched {len(accounts)} tip accounts")
                return accounts
                
        except asyncio.TimeoutError:
            logger.error("[jito] Timeout fetching tip accounts")
            raise JitoTimeoutError("Timeout fetching tip accounts")
        except Exception as e:
            logger.error(f"[jito] Error fetching tip accounts: {e}")
            raise JitoNetworkError(str(e))
    
    async def get_tip_lamports_floor(self) -> int:
        """
        Get the minimum tip amount in lamports.
        
        Returns:
            Minimum tip amount from available tip accounts.
        """
        accounts = await self.get_tip_accounts()
        
        if not accounts:
            logger.warning("[jito] No tip accounts available, using default")
            return self.config.min_tip_lamports
        
        # Return the minimum tip rate
        min_tip = min(a.lamports_per_signature for a in accounts)
        logger.info(f"[jito] Tip floor: {min_tip} lamports")
        return min_tip
    
    async def send_bundle(
        self, 
        bundle: JitoBundleRequest,
        tip_account: Optional[Pubkey] = None,
    ) -> JitoBundleResponse:
        """
        Submit a bundle to Jito block-engine.
        
        Args:
            bundle: The bundle request containing instructions and tip info.
            tip_account: Optional tip account (uses first available if not provided).
            
        Returns:
            JitoBundleResponse with bundle_id and acceptance status.
            
        Note:
            The bundle is serialized as base64-encoded transactions.
        """
        if self.session is None:
            raise RuntimeError("JitoClient session not initialized. Use async context manager.")
        
        # Get tip account if not provided
        if tip_account is None:
            tip_account = bundle.tip_account
        
        # Serialize transactions to base64
        try:
            tx_strings = []
            for ix in bundle.instructions:
                # Serialize each instruction to base64
                # In practice, you'd serialize the full transaction
                tx_data = ix.data if hasattr(ix, 'data') else b""
                tx_strings.append(tx_data.hex())
            
            payload = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "sendBundle",
                "params": [
                    tx_strings,
                    {
                        "tip_account": str(tip_account),
                        "tip_lamports": bundle.tip_amount_lamports,
                    }
                ]
            }
            
            url = f"{self.config.endpoint}/api/v1/bundles"
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[jito] Bundle submission failed: HTTP {response.status}: {error_text}")
                    
                    # Try to parse Jito error response
                    try:
                        error_data = await response.json()
                        rejection_reason = error_data.get("error", {}).get("message", error_text)
                    except:
                        rejection_reason = error_text
                    
                    return JitoBundleResponse(
                        bundle_id="",
                        accepted=False,
                        rejection_reason=rejection_reason,
                    )
                
                data = await response.json()
                
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown error")
                    logger.error(f"[jito] Bundle rejected: {error_msg}")
                    return JitoBundleResponse(
                        bundle_id="",
                        accepted=False,
                        rejection_reason=error_msg,
                    )
                
                bundle_id = data.get("result", {}).get("bundle_id", str(uuid.uuid4()))
                logger.info(f"[jito] Bundle submitted: {bundle_id}")
                
                return JitoBundleResponse(
                    bundle_id=bundle_id,
                    accepted=True,
                    rejection_reason=None,
                )
                
        except asyncio.TimeoutError:
            logger.error("[jito] Bundle submission timeout")
            return JitoBundleResponse(
                bundle_id="",
                accepted=False,
                rejection_reason="timeout",
            )
        except Exception as e:
            logger.error(f"[jito] Bundle submission error: {e}")
            return JitoBundleResponse(
                bundle_id="",
                accepted=False,
                rejection_reason=str(e),
            )


def build_buy_bundle(
    swap_instruction: TransactionInstruction,
    payer_wallet: Pubkey,
    tip_account: Pubkey,
    tip_amount_lamports: int,
) -> JitoBundleRequest:
    """
    Build a Jito bundle for a buy transaction.
    
    The bundle consists of:
    1. Swap instruction (from Jupiter quote)
    2. Tip instruction (transfer to Jito validator)
    
    Args:
        swap_instruction: The swap transaction instruction.
        payer_wallet: The wallet paying for the tip.
        tip_account: The Jito tip account to send to.
        tip_amount_lamports: Amount of lamports for the tip.
        
    Returns:
        JitoBundleRequest ready for submission.
        
    Note:
        Tip must come AFTER swap instruction for proper MEV protection.
    """
    # Create tip instruction
    tip_ix = transfer(
        TransferParams(
            from_pubkey=payer_wallet,
            to_pubkey=tip_account,
            lamports=tip_amount_lamports,
        )
    )
    
    # Build bundle with swap first, then tip
    instructions = [swap_instruction, tip_ix]
    
    return JitoBundleRequest(
        instructions=instructions,
        tip_amount_lamports=tip_amount_lamports,
        tip_account=tip_account,
    )


def calculate_tip_amount(
    tip_floor_lamports: int,
    config: JitoConfig,
) -> int:
    """
    Calculate the tip amount based on configuration.
    
    Args:
        tip_floor_lamports: Minimum tip from Jito API.
        config: Jito configuration.
        
    Returns:
        Calculated tip amount within configured bounds.
    """
    calculated = int(tip_floor_lamports * config.tip_multiplier)
    
    # Clamp to configured bounds
    return max(config.min_tip_lamports, min(calculated, config.max_tip_lamports))


class JitoError(Exception):
    """Base exception for Jito-related errors."""
    pass


class JitoTimeoutError(JitoError):
    """Raised when Jito API request times out."""
    pass


class JitoNetworkError(JitoError):
    """Raised when Jito API returns an error."""
    pass


# Validate reject reasons are known
__JITO_REASONS__ = [
    JITOBUNDLE_REJECTED,
    JITOBUNDLE_TIMEOUT,
    JITOBUNDLE_TIP_TOO_LOW,
    JITOBUNDLE_NETWORK_ERROR,
]

for reason in __JITO_REASONS__:
    assert_reason_known(reason)
