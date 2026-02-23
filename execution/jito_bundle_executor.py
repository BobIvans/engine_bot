"""
Jito Bundle Executor (PR-G.4)

Provides JitoClient abstraction for bundle submission.
"""

import asyncio
import importlib
import importlib.util
import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional

from execution.jito_structs import (
    JitoBundleRequest,
    JitoBundleResponse,
    JitoConfig,
    JitoTipAccount,
    Pubkey,
    TransactionInstruction,
)
from integration.reject_reasons import (
    JITOBUNDLE_NETWORK_ERROR,
    JITOBUNDLE_REJECTED,
    JITOBUNDLE_TIMEOUT,
    JITOBUNDLE_TIP_TOO_LOW,
    assert_reason_known,
)

logger = logging.getLogger(__name__)

_HAS_AIOHTTP = importlib.util.find_spec("aiohttp") is not None
_HAS_SOLANA_SYSTEM = importlib.util.find_spec("solana") is not None

if _HAS_AIOHTTP:
    aiohttp = importlib.import_module("aiohttp")
else:
    aiohttp = None

if _HAS_SOLANA_SYSTEM:
    solana_system_program = importlib.import_module("solana.system_program")
else:
    solana_system_program = None


@dataclass
class JitoClient:
    config: JitoConfig
    session: Optional[object] = None
    _tip_accounts_cache: Optional[List[JitoTipAccount]] = None
    _cache_timestamp: float = 0.0

    async def __aenter__(self):
        if self.session is None:
            if not _HAS_AIOHTTP:
                raise RuntimeError("aiohttp is required for live Jito API usage")
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None

    async def get_tip_accounts(self) -> List[JitoTipAccount]:
        import time

        current_time = time.time()
        if self._tip_accounts_cache is not None and current_time - self._cache_timestamp < 60:
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
                accounts: List[JitoTipAccount] = []
                for item in data.get("accounts", []):
                    accounts.append(
                        JitoTipAccount(
                            account=Pubkey.from_string(item["account"]),
                            lamports_per_signature=item.get("lamports_per_signature", 0),
                        )
                    )

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
        accounts = await self.get_tip_accounts()
        if not accounts:
            logger.warning("[jito] No tip accounts available, using default")
            return self.config.min_tip_lamports
        return min(a.lamports_per_signature for a in accounts)

    async def send_bundle(
        self,
        bundle: JitoBundleRequest,
        tip_account: Optional[Pubkey] = None,
    ) -> JitoBundleResponse:
        if self.session is None:
            raise RuntimeError("JitoClient session not initialized. Use async context manager.")

        if tip_account is None:
            tip_account = bundle.tip_account

        try:
            tx_strings = []
            for ix in bundle.instructions:
                tx_data = ix.data if hasattr(ix, "data") else b""
                tx_strings.append(tx_data.hex() if isinstance(tx_data, (bytes, bytearray)) else str(tx_data))

            payload = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "sendBundle",
                "params": [
                    tx_strings,
                    {"tip_account": str(tip_account), "tip_lamports": bundle.tip_amount_lamports},
                ],
            }

            url = f"{self.config.endpoint}/api/v1/bundles"

            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[jito] Bundle submission failed: HTTP {response.status}: {error_text}")
                    return JitoBundleResponse(bundle_id="", accepted=False, rejection_reason=error_text)

                data = await response.json()
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown error")
                    logger.error(f"[jito] Bundle rejected: {error_msg}")
                    return JitoBundleResponse(bundle_id="", accepted=False, rejection_reason=error_msg)

                bundle_id = data.get("result", {}).get("bundle_id", str(uuid.uuid4()))
                return JitoBundleResponse(bundle_id=bundle_id, accepted=True, rejection_reason=None)
        except asyncio.TimeoutError:
            logger.error("[jito] Bundle submission timeout")
            return JitoBundleResponse(bundle_id="", accepted=False, rejection_reason="timeout")
        except Exception as e:
            logger.error(f"[jito] Bundle submission error: {e}")
            return JitoBundleResponse(bundle_id="", accepted=False, rejection_reason=str(e))


def build_buy_bundle(
    swap_instruction: TransactionInstruction,
    payer_wallet: Pubkey,
    tip_account: Pubkey,
    tip_amount_lamports: int,
) -> JitoBundleRequest:
    if _HAS_SOLANA_SYSTEM:
        tip_ix = solana_system_program.transfer(
            solana_system_program.TransferParams(
                from_pubkey=payer_wallet,
                to_pubkey=tip_account,
                lamports=tip_amount_lamports,
            )
        )
    else:
        @dataclass
        class _FallbackTipIx:
            data: bytes

        tip_ix = _FallbackTipIx(data=f"tip:{tip_amount_lamports}:{tip_account}".encode())

    return JitoBundleRequest(
        instructions=[swap_instruction, tip_ix],
        tip_amount_lamports=tip_amount_lamports,
        tip_account=tip_account,
    )


def calculate_tip_amount(tip_floor_lamports: int, config: JitoConfig) -> int:
    calculated = int(tip_floor_lamports * config.tip_multiplier)
    return max(config.min_tip_lamports, min(calculated, config.max_tip_lamports))


class JitoError(Exception):
    pass


class JitoTimeoutError(JitoError):
    pass


class JitoNetworkError(JitoError):
    pass


__JITO_REASONS__ = [
    JITOBUNDLE_REJECTED,
    JITOBUNDLE_TIMEOUT,
    JITOBUNDLE_TIP_TOO_LOW,
    JITOBUNDLE_NETWORK_ERROR,
]

for reason in __JITO_REASONS__:
    assert_reason_known(reason)
