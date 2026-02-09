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
from typing import List, Optional
from solders.pubkey import Pubkey
from solana.transaction import TransactionInstruction


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
    """
    Response from Jito bundle submission.
    
    Attributes:
        bundle_id: Unique identifier for tracking the bundle
        accepted: Whether the bundle was accepted for processing
        rejection_reason: Reason for rejection if not accepted
    """
    bundle_id: str
    accepted: bool
    rejection_reason: Optional[str] = None


@dataclass
class JitoTipAccount:
    """
    A Jito validator tip account.
    
    Attributes:
        account: Public key of the tip account
        lamports_per_signature: Current tip rate for this account
    """
    account: Pubkey
    lamports_per_signature: int


@dataclass
class JitoTipAccountsResponse:
    """
    Response from Jito /tip-accounts endpoint.
    
    Attributes:
        accounts: List of available tip accounts
        valid_for_next_n_slots: How long these accounts are valid
    """
    accounts: List[JitoTipAccount]
    valid_for_next_n_slots: int


@dataclass
class JitoConfig:
    """
    Configuration for Jito bundle execution.
    
    Attributes:
        enabled: Whether Jito bundles are enabled
        endpoint: Jito block-engine endpoint
        tip_multiplier: Multiplier for tip amount (e.g., 1.2 = 20% above floor)
        min_tip_lamports: Minimum tip amount in lamports
        max_tip_lamports: Maximum tip amount in lamports
        timeout_seconds: Timeout for bundle submission
    """
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
JITO_TIP_ACCOUNT_SIZE = 96  # Size of tip account state
