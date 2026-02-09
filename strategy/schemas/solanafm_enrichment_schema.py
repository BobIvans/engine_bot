"""
Pydantic schema for SolanaFM token enrichment data.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SolanaFMEnrichment(BaseModel):
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
    
    mint: str = Field(..., description="Token mint address")
    is_verified: bool = Field(False, description="Whether token is verified on SolanaFM")
    creator_address: Optional[str] = Field(None, description="Token creator address")
    top_holder_pct: float = Field(100.0, ge=0, le=100, description="Top 10 holders percentage")
    holder_count: int = Field(0, ge=0, description="Total number of token holders")
    has_mint_authority: bool = Field(False, description="Whether mint authority exists")
    has_freeze_authority: bool = Field(False, description="Whether freeze authority exists")
    enrichment_ts: int = Field(..., ge=0, description="Unix timestamp of enrichment")
    source: str = Field("unknown", description="Data source: api, fallback, fixture")
    
    @field_validator("mint")
    @classmethod
    def validate_mint(cls, v: str) -> str:
        """Validate Solana mint address format."""
        if not v:
            raise ValueError("mint cannot be empty")
        # Basic length check for Solana addresses
        if len(v) < 32 or len(v) > 44:
            raise ValueError(f"Invalid mint address length: {len(v)}")
        return v
    
    @field_validator("creator_address")
    @classmethod
    def validate_creator(cls, v: Optional[str]) -> Optional[str]:
        """Validate creator address if provided."""
        if v is not None and len(v) < 32:
            raise ValueError(f"Invalid creator address length: {len(v)}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "is_verified": True,
                "creator_address": "GoSq3sNVHbMc7xQ7jY48X3vNM6hG9X3Y8Z3K1p9Q2r4",
                "top_holder_pct": 15.5,
                "holder_count": 15234,
                "has_mint_authority": False,
                "has_freeze_authority": False,
                "enrichment_ts": 1704067200,
                "source": "api"
            }
        }


def validate_solanafm_enrichment(data: dict) -> SolanaFMEnrichment:
    """Validate enrichment data against schema."""
    return SolanaFMEnrichment(**data)
