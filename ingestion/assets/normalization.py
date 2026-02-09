"""
ingestion/assets/normalization.py

Normalization of Helius DAS API responses to flat structures.

PR-T.4
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AssetData:
    """Normalized asset ownership data."""
    asset_id: str           # Asset ID (mint or compressed ID)
    mint_address: Optional[str]  # For fungible tokens, the mint address
    owner: str              # Owner wallet address
    balance: int            # Token balance (for SPL tokens)
    decimals: int            # Token decimals
    symbol: Optional[str]   # Token symbol (if available)
    name: Optional[str]     # Token name
    is_fungible: bool       # True for SPL tokens, False for NFTs
    is_nft: bool            # True for NFTs
    interface: str          # Interface type (e.g., "FUNGIBLE", "NFT")
    
    # Metadata flags (important for security)
    is_mutable: bool        # Can metadata be changed?
    has_freeze_authority: bool  # Does someone have freeze authority?
    is_frozen: bool         # Is the asset currently frozen?
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "mint_address": self.mint_address,
            "owner": self.owner,
            "balance": self.balance,
            "decimals": self.decimals,
            "symbol": self.symbol,
            "name": self.name,
            "is_fungible": self.is_fungible,
            "is_nft": self.is_nft,
            "interface": self.interface,
            "is_mutable": self.is_mutable,
            "has_freeze_authority": self.has_freeze_authority,
            "is_frozen": self.is_frozen,
        }


@dataclass
class AssetMetadata:
    """Normalized asset metadata."""
    asset_id: str           # Asset ID
    name: Optional[str]     # Asset name
    symbol: Optional[str]   # Asset symbol
    uri: Optional[str]      # Off-chain URI (for NFTs)
    mint_address: Optional[str]  # Mint address
    
    # Token info
    decimals: int           # Token decimals
    supply: Optional[int]   # Total supply
    
    # Authorities
    freeze_authority: Optional[str]  # Freeze authority address
    mint_authority: Optional[str]    # Mint authority address
    update_authority: Optional[str]  # Update authority address
    
    # Security flags
    is_mutable: bool        # Can metadata be changed?
    is_verified_creator: bool  # Has a verified creator?
    is_creator: bool        # Is the requesting wallet a creator?
    
    # Extensions (for advanced checks)
    extensions: List[str] = field(default_factory=list)
    
    # Raw data for debugging
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "symbol": self.symbol,
            "uri": self.uri,
            "mint_address": self.mint_address,
            "decimals": self.decimals,
            "supply": self.supply,
            "freeze_authority": self.freeze_authority,
            "mint_authority": self.mint_authority,
            "update_authority": self.update_authority,
            "is_mutable": self.is_mutable,
            "is_verified_creator": self.is_verified_creator,
            "is_creator": self.is_creator,
            "extensions": self.extensions,
        }
    
    def has_freeze_authority_check(self) -> bool:
        """Check if freeze authority exists (important for security)."""
        return self.freeze_authority is not None
    
    def is_safe_for_trading(self) -> bool:
        """Check if asset is safe for trading based on metadata."""
        # Check if metadata is immutable (safer)
        if self.is_mutable:
            return False
        
        # Check if freeze authority exists (could be used to freeze user funds)
        if self.has_freeze_authority_check():
            return False
        
        return True


def normalize_asset(data: Dict[str, Any]) -> Optional[AssetData]:
    """
    Normalize getAssetsByOwner response to AssetData.
    
    Args:
        data: Raw asset data from Helius DAS API
        
    Returns:
        Normalized AssetData or None if parsing fails
    """
    try:
        # Extract basic fields
        asset_id = data.get("id", "")
        
        # Determine if fungible or NFT
        interface = data.get("interface", "").upper()
        is_fungible = interface == "FUNGIBLE"
        is_nft = interface in ("NFT", "NON_FUNGIBLE")
        
        # Get ownership info
        ownership = data.get("ownership", {})
        owner = ownership.get("owner", "")
        
        # Get token info (for fungible tokens)
        token_info = data.get("token_info", {})
        balance = token_info.get("balance", 0)
        decimals = token_info.get("decimals", 0)
        
        # Get metadata
        metadata = data.get("metadata", {})
        symbol = metadata.get("symbol", "") or None
        name = metadata.get("name", "") or None
        
        # Get mint address
        mint_address = data.get("mint", "") or None
        
        # Check security flags
        is_mutable = data.get("is_mutable", True)
        
        # Check authorities
        authorities = data.get("authorities", [])
        has_freeze_authority = any(
            a.get("address") and "freeze" in a.get("kind", "").lower()
            for a in authorities
        )
        
        # Check if frozen
        is_frozen = data.get("frozen", False)
        
        return AssetData(
            asset_id=asset_id,
            mint_address=mint_address,
            owner=owner,
            balance=balance,
            decimals=decimals,
            symbol=symbol,
            name=name,
            is_fungible=is_fungible,
            is_nft=is_nft,
            interface=interface,
            is_mutable=is_mutable,
            has_freeze_authority=has_freeze_authority,
            is_frozen=is_frozen,
        )
        
    except Exception as e:
        return None


def normalize_metadata(data: Dict[str, Any]) -> Optional[AssetMetadata]:
    """
    Normalize getAsset/getAssetBatch response to AssetMetadata.
    
    Args:
        data: Raw metadata from Helius DAS API
        
    Returns:
        Normalized AssetMetadata or None if parsing fails
    """
    try:
        asset_id = data.get("id", "")
        
        # Basic info
        name = data.get("name", "") or None
        symbol = data.get("symbol", "") or None
        uri = data.get("uri", "") or None
        
        # Mint address
        mint_address = data.get("mint", "") or None
        
        # Token info
        token_info = data.get("token_info", {})
        decimals = token_info.get("decimals", 0)
        supply = token_info.get("supply", None)
        
        # Authorities
        authorities = data.get("authorities", [])
        freeze_authority = None
        mint_authority = None
        update_authority = None
        
        for auth in authorities:
            auth_address = auth.get("address", "")
            auth_kind = auth.get("kind", "").upper()
            
            if "FREEZE" in auth_kind:
                freeze_authority = auth_address
            elif "MINT" in auth_kind:
                mint_authority = auth_address
            elif "UPDATE" in auth_kind:
                update_authority = auth_address
        
        # Security flags
        is_mutable = data.get("is_mutable", True)
        
        # Creator info
        creators = data.get("creators", [])
        is_verified_creator = any(c.get("verified", False) for c in creators)
        is_creator = any(c.get("address", "") and c.get("verified", False) for c in creators)
        
        # Extensions (for advanced checks)
        mint_extensions = data.get("mint_extensions", [])
        extensions = []
        for ext in mint_extensions:
            ext_type = ext.get("type", "")
            if ext_type:
                extensions.append(ext_type)
        
        return AssetMetadata(
            asset_id=asset_id,
            name=name,
            symbol=symbol,
            uri=uri,
            mint_address=mint_address,
            decimals=decimals,
            supply=supply,
            freeze_authority=freeze_authority,
            mint_authority=mint_authority,
            update_authority=update_authority,
            is_mutable=is_mutable,
            is_verified_creator=is_verified_creator,
            is_creator=is_creator,
            extensions=extensions,
            raw_data=data,
        )
        
    except Exception as e:
        return None


def filter_unsafe_assets(assets: List[AssetData]) -> List[AssetData]:
    """
    Filter out unsafe assets (mutable metadata or freeze authority).
    
    Args:
        assets: List of normalized AssetData
        
    Returns:
        List of safe assets only
    """
    safe = []
    for asset in assets:
        # Skip if metadata can be changed
        if asset.is_mutable:
            continue
        
        # Skip if freeze authority exists
        if asset.has_freeze_authority:
            continue
        
        safe.append(asset)
    
    return safe


def get_token_summary(assets: List[AssetData]) -> Dict[str, Any]:
    """
    Generate a summary of token holdings.
    
    Args:
        assets: List of normalized AssetData
        
    Returns:
        Summary dict with counts and values
    """
    fungible = [a for a in assets if a.is_fungible]
    nfts = [a for a in assets if a.is_nft]
    
    return {
        "total_assets": len(assets),
        "fungible_tokens": len(fungible),
        "nfts": len(nfts),
        "symbols": list(set(a.symbol for a in fungible if a.symbol)),
        "has_scam_risk": len(assets) != len(filter_unsafe_assets(assets)),
    }
