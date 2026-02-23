"""
Jito Bundle Structures (PR-G.4)

Data classes for Jito bundle execution:
- JitoBundleRequest: Request to send a bundle
- JitoBundleResponse: Response from Jito API
- JitoTipAccounts: Response from /tip-accounts endpoint

HARD RULES:
- Jito logic NEVER activates in paper/sim modes
- All errors logged to stderr with reject reason
- No real network calls in smoke tests (use mocks)
"""

from dataclasses import dataclass
import importlib
import importlib.util
from typing import Any, List, Optional


# Optional dependency: solders
if importlib.util.find_spec("solders") is not None:
    Pubkey = importlib.import_module("solders.pubkey").Pubkey
else:
    class Pubkey:
        """Lightweight fallback for environments without solders."""

        def __init__(self, value: str):
            self._value = value

        @classmethod
        def from_string(cls, value: str) -> "Pubkey":
            return cls(value)

        def __str__(self) -> str:
            return self._value

        def __repr__(self) -> str:
            return f"Pubkey('{self._value}')"

        def __eq__(self, other: object) -> bool:
            if isinstance(other, Pubkey):
                return self._value == other._value
            return str(other) == self._value


# Optional dependency: solana
if importlib.util.find_spec("solana") is not None:
    TransactionInstruction = importlib.import_module("solana.transaction").TransactionInstruction
else:
    TransactionInstruction = Any


@dataclass
class JitoBundleRequest:
    """
    Request to send a Jito bundle.

    A bundle consists of multiple transactions that are executed atomically.
    For buy transactions, the typical order is:
    1. Swap instruction (Jupiter/Raydium)
    2. Tip instruction (transfer to Jito validator)
    """

    instructions: List[TransactionInstruction]
    tip_amount_lamports: int
    tip_account: Pubkey

    def __post_init__(self):
        if not self.instructions:
            raise ValueError("Bundle must contain at least one instruction")
        if self.tip_amount_lamports < 0:
            raise ValueError("Tip amount cannot be negative")


@dataclass
class JitoBundleResponse:
    bundle_id: str
    accepted: bool
    rejection_reason: Optional[str] = None


@dataclass
class JitoTipAccount:
    account: Pubkey
    lamports_per_signature: int


@dataclass
class JitoTipAccountsResponse:
    accounts: List[JitoTipAccount]
    valid_for_next_n_slots: int


@dataclass
class JitoConfig:
    enabled: bool = False
    endpoint: str = "https://mainnet.block-engine.jito.wtf"
    tip_multiplier: float = 1.2
    min_tip_lamports: int = 10000
    max_tip_lamports: int = 500000
    timeout_seconds: int = 30

    def __post_init__(self):
        if self.tip_multiplier <= 0:
            raise ValueError("Tip multiplier must be positive")
        if self.min_tip_lamports > self.max_tip_lamports:
            raise ValueError("Min tip cannot be greater than max tip")


# Jito Tip Program constants
JITO_TIP_PROGRAM_ID = Pubkey.from_string("TiptapColum321Ruy2Vw491v33DdseG66XCXAZXz4LH")
JITO_TIP_ACCOUNT_SIZE = 96
