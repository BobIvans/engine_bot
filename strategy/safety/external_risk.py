"""
Pure logic for parsing RugCheck API responses.

Transforms raw JSON responses into normalized risk profiles.
This module contains NO network calls — only data transformation.

Output format: risk_eval.v1
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import json


@dataclass
class RiskProfile:
    """Normalized risk evaluation result."""
    mint: str
    provider: str  # e.g., "rugcheck"
    score: float   # 0.0 = Safe, 1.0 = Scam
    flags: List[str]
    timestamp: int  # Unix timestamp of evaluation
    is_verified: bool = False
    top_holder_concentration: float = 0.0  # 0-1 scale
    
    def to_dict(self) -> dict:
        return {
            "mint": self.mint,
            "provider": self.provider,
            "score": round(self.score, 4),
            "flags": self.flags,
            "timestamp": self.timestamp,
            "is_verified": self.is_verified,
            "top_holder_concentration": round(self.top_holder_concentration, 4),
        }


# Risk weights for different flags
FLAG_WEIGHTS = {
    "mint_authority_enabled": 0.30,
    "freeze_authority_enabled": 0.30,
    "top_holder_concentration_high": 0.20,
    "owner_is_creator": 0.10,
    "lp_burned": -0.05,  # Negative risk (good sign)
    "verified": -0.20,   # Negative risk (good sign)
    "no_special_mints": -0.10,  # Negative risk (good sign)
}


def normalize_rugcheck_report(raw_report: Dict) -> RiskProfile:
    """
    Normalize RugCheck API response into a RiskProfile.
    
    Args:
        raw_report: Raw JSON dict from RugCheck API
        
    Returns:
        RiskProfile with normalized score (0-1) and flags
        
    Scoring Logic:
        - Start with base score of 0.0 (Safe)
        - Add weights for each risk flag found
        - Clamp to [0.0, 1.0] range
    """
    # Extract basic fields
    mint = raw_report.get("mint", raw_report.get("tokenAddress", ""))
    timestamp = raw_report.get("timestamp", raw_report.get("listedAt", 0))
    
    # Handle nested result structure
    result = raw_report.get("result", raw_report)
    
    # Extract flags from the report
    flags: List[str] = []
    
    # Check mint authority
    if result.get("mintAuthority", {}).get("type") != "none":
        flags.append("mint_authority_enabled")
    
    # Check freeze authority
    if result.get("freezeAuthority", {}).get("type") != "none":
        flags.append("freeze_authority_enabled")
    
    # Check top holder concentration
    top_holders = result.get("topHolders", [])
    if top_holders:
        # Calculate concentration (sum of top 10 holders)
        total_supply = result.get("supply", 1)
        if total_supply > 0:
            top_10_sum = sum(h.get("amount", 0) for h in top_holders[:10])
            concentration = top_10_sum / total_supply
        else:
            concentration = 0.0
        
        if concentration > 0.8:
            flags.append("top_holder_concentration_high")
    
    # Check if owner is creator (potential rug)
    if result.get("owner") == result.get("creator"):
        flags.append("owner_is_creator")
    
    # Check for good signs (negative risk)
    if result.get("lpBurned", False):
        flags.append("lp_burned")
    
    if result.get("verified", False):
        flags.append("verified")
    
    if result.get("noSpecialMints", True):
        flags.append("no_special_mints")
    
    # Calculate normalized score
    score = 0.0
    for flag in flags:
        weight = FLAG_WEIGHTS.get(flag, 0.0)
        score += weight
    
    # Clamp score to [0.0, 1.0]
    score = max(0.0, min(1.0, score))
    
    # Extract additional metadata
    is_verified = result.get("verified", False)
    top_holder_concentration = 0.0
    if top_holders:
        total_supply = result.get("supply", 1)
        if total_supply > 0:
            top_10_sum = sum(h.get("amount", 0) for h in top_holders[:10])
            top_holder_concentration = top_10_sum / total_supply
    
    return RiskProfile(
        mint=mint,
        provider="rugcheck",
        score=score,
        flags=flags,
        timestamp=timestamp,
        is_verified=is_verified,
        top_holder_concentration=top_holder_concentration,
    )


def format_output(profile: RiskProfile) -> dict:
    """Format risk profile for JSON output (risk_eval.v1 format)."""
    output = profile.to_dict()
    output["version"] = "risk_eval.v1"
    return output


if __name__ == "__main__":
    # Test with mock data
    mock_good = {
        "mint": "So11111111111111111111111111111111111111112",
        "timestamp": 1704067200,
        "result": {
            "mintAuthority": {"type": "none"},
            "freezeAuthority": {"type": "none"},
            "topHolders": [{"amount": 1000000}, {"amount": 500000}, {"amount": 400000}],
            "supply": 10000000,
            "owner": "Owner123",
            "creator": "Creator456",
            "lpBurned": True,
            "verified": True,
            "noSpecialMints": True,
        }
    }
    
    mock_bad = {
        "mint": "Rug1111111111111111111111111111111111111111",
        "timestamp": 1704067200,
        "result": {
            "mintAuthority": {"type": "mintable"},
            "freezeAuthority": {"type": "freezeable"},
            "topHolders": [{"amount": 9000000}, {"amount": 500000}, {"amount": 400000}],
            "supply": 10000000,
            "owner": "Scammer123",
            "creator": "Scammer123",  # Same as owner
            "lpBurned": False,
            "verified": False,
            "noSpecialMints": False,
        }
    }
    
    good_profile = normalize_rugcheck_report(mock_good)
    bad_profile = normalize_rugcheck_report(mock_bad)
    
    print("Good Token Risk Profile:")
    print(json.dumps(format_output(good_profile), indent=2))
    print("\nBad Token Risk Profile:")
    print(json.dumps(format_output(bad_profile), indent=2))
