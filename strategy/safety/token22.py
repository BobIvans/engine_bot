"""
Pure logic for Token-2022 Extension Analysis.

Analyzes SPL Token-2022 extensions to detect hidden risks:
- TransferHook: Programmable transfer logic (taxes/blocks)
- PermanentDelegate: Admin can burn/revoke tokens
- DefaultAccountState: Frozen by default
- MintCloseAuthority: Can close mint account

Output format: token_extensions.v1.jsonl
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class RiskSeverity(Enum):
    """Risk severity levels."""
    NONE = "none"
    MEDIUM = "medium"
    HIGH = "high"


# Risk flag constants
FLAG_CLEAN = "CLEAN"
FLAG_TRANSFER_HOOK = "HAS_TRANSFER_HOOK"
FLAG_PERMANENT_DELEGATE = "HAS_PERMANENT_DELEGATE"
FLAG_DEFAULT_FROZEN = "DEFAULT_FROZEN"
FLAG_MINT_CLOSE_AUTH = "HAS_MINT_CLOSE_AUTH"
FLAG_TRANSFER_FEE = "HAS_TRANSFER_FEE"
FLAG_NON_TRANSFERABLE = "NON_TRANSFERABLE"

# Extension to risk flag mapping
EXTENSION_RISK_MAP: Dict[str, tuple] = {
    "transferHook": (FLAG_TRANSFER_HOOK, RiskSeverity.HIGH),
    "permanentDelegate": (FLAG_PERMANENT_DELEGATE, RiskSeverity.HIGH),
    "defaultAccountState": (FLAG_DEFAULT_FROZEN, RiskSeverity.HIGH),  # Checked for frozen state
    "mintCloseAuthority": (FLAG_MINT_CLOSE_AUTH, RiskSeverity.MEDIUM),
    "transferFeeConfig": (FLAG_TRANSFER_FEE, RiskSeverity.MEDIUM),
    "nonTransferable": (FLAG_NON_TRANSFERABLE, RiskSeverity.HIGH),
}

# Extensions that trigger blocking
BLOCKING_FLAGS = {
    FLAG_TRANSFER_HOOK,
    FLAG_PERMANENT_DELEGATE,
    FLAG_DEFAULT_FROZEN,
    FLAG_NON_TRANSFERABLE,
}


@dataclass
class TokenSecurityProfile:
    """Security profile for a Token-2022 mint."""
    mint: str
    extensions: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    is_blocked: bool = False
    
    def to_dict(self) -> dict:
        return {
            "mint": self.mint,
            "extensions": self.extensions,
            "risk_flags": self.risk_flags,
            "is_blocked": self.is_blocked,
        }


def analyze_extensions(
    mint: str,
    extensions: List[Dict[str, Any]]
) -> TokenSecurityProfile:
    """
    Analyze Token-2022 extensions and return security profile.
    
    Args:
        mint: Token mint address
        extensions: List of extension objects from RPC getAccountInfo
                    e.g. [{"extension": "transferHook", "state": {...}}]
    
    Returns:
        TokenSecurityProfile with risk flags and block status
    """
    extension_names: List[str] = []
    risk_flags: List[str] = []
    
    for ext in extensions:
        ext_type = ext.get("extension", "")
        extension_names.append(ext_type)
        
        # Check if this extension is risky
        if ext_type in EXTENSION_RISK_MAP:
            flag, severity = EXTENSION_RISK_MAP[ext_type]
            
            # Special handling for defaultAccountState - only risky if frozen
            if ext_type == "defaultAccountState":
                state = ext.get("state", {})
                account_state = state.get("state", "")
                if account_state.lower() == "frozen":
                    risk_flags.append(flag)
            else:
                risk_flags.append(flag)
    
    # Determine if clean
    if not risk_flags:
        risk_flags.append(FLAG_CLEAN)
    
    # Determine if should be blocked
    is_blocked = any(flag in BLOCKING_FLAGS for flag in risk_flags)
    
    return TokenSecurityProfile(
        mint=mint,
        extensions=extension_names,
        risk_flags=risk_flags,
        is_blocked=is_blocked,
    )


def analyze_extensions_from_account_info(
    mint: str,
    account_info: Optional[Dict[str, Any]]
) -> TokenSecurityProfile:
    """
    Analyze extensions from raw account info JSON.
    
    Args:
        mint: Token mint address
        account_info: Raw account info with 'extensions' field
        
    Returns:
        TokenSecurityProfile
    """
    if account_info is None:
        return TokenSecurityProfile(
            mint=mint,
            extensions=[],
            risk_flags=[FLAG_CLEAN],
            is_blocked=False,
        )
    
    extensions = account_info.get("extensions", [])
    return analyze_extensions(mint, extensions)


def format_output(profiles: List[TokenSecurityProfile]) -> dict:
    """Format profiles for JSON summary output."""
    blocked_count = sum(1 for p in profiles if p.is_blocked)
    return {
        "version": "token_extensions.v1",
        "total": len(profiles),
        "blocked": blocked_count,
        "clean": len(profiles) - blocked_count,
    }


if __name__ == "__main__":
    # Simple test
    import json
    
    # Test 1: Clean token (no extensions)
    profile1 = analyze_extensions("CleanMint", [])
    print(f"Clean token: {json.dumps(profile1.to_dict())}")
    
    # Test 2: TransferHook token
    profile2 = analyze_extensions("HookMint", [
        {"extension": "transferHook", "state": {"authority": "xxx"}}
    ])
    print(f"Hook token: {json.dumps(profile2.to_dict())}")
    
    # Test 3: Multiple risky extensions
    profile3 = analyze_extensions("RiskyMint", [
        {"extension": "transferHook", "state": {}},
        {"extension": "permanentDelegate", "state": {}},
    ])
    print(f"Risky token: {json.dumps(profile3.to_dict())}")
    
    # Test 4: DefaultAccountState frozen
    profile4 = analyze_extensions("FrozenMint", [
        {"extension": "defaultAccountState", "state": {"state": "frozen"}}
    ])
    print(f"Frozen token: {json.dumps(profile4.to_dict())}")
