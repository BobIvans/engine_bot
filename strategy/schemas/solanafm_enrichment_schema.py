"""
Schema for SolanaFM token enrichment data.

This module intentionally avoids optional third-party dependencies so smoke
checks can run in minimal environments.
"""

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class SolanaFMEnrichment:
    """
    Token enrichment data from SolanaFM API.

    Fields:
    - mint: Token mint address
    - is_verified: Whether token is verified
    - creator_address: Token creator address
    - top_holder_pct: Percentage held by top 10 holders
    - holder_count: Total number of holders
    - has_mint_authority: Whether mint authority exists
    - has_freeze_authority: Whether freeze authority exists
    - enrichment_ts: Unix timestamp of enrichment
    - source: Data source ('api', 'fallback', 'fixture')
    """

    mint: str
    is_verified: bool = False
    creator_address: Optional[str] = None
    top_holder_pct: float = 100.0
    holder_count: int = 0
    has_mint_authority: bool = False
    has_freeze_authority: bool = False
    enrichment_ts: int = 0
    source: str = "unknown"

    def __post_init__(self) -> None:
        self._validate_mint(self.mint)
        self._validate_creator(self.creator_address)

        if not (0 <= float(self.top_holder_pct) <= 100):
            raise ValueError("top_holder_pct must be between 0 and 100")
        if int(self.holder_count) < 0:
            raise ValueError("holder_count must be >= 0")
        if int(self.enrichment_ts) < 0:
            raise ValueError("enrichment_ts must be >= 0")

        # Normalize numeric field types for consistent downstream behavior.
        self.top_holder_pct = float(self.top_holder_pct)
        self.holder_count = int(self.holder_count)
        self.enrichment_ts = int(self.enrichment_ts)

    @staticmethod
    def _validate_mint(value: str) -> None:
        if not value:
            raise ValueError("mint cannot be empty")
        if len(value) < 32:
            raise ValueError(f"Invalid mint address length: {len(value)}")

    @staticmethod
    def _validate_creator(value: Optional[str]) -> None:
        if value is not None and len(value) < 32:
            raise ValueError(f"Invalid creator address length: {len(value)}")

    def dict(self) -> dict:
        """Pydantic-compatible dictionary export used by callers."""
        return asdict(self)


# Backwards-compatible helper used by adapter and smoke tests.
def validate_solanafm_enrichment(data: dict) -> SolanaFMEnrichment:
    """Validate enrichment data against schema."""
    return SolanaFMEnrichment(**data)
