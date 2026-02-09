"""
ingestion/assets/das_client.py

Helius Digital Asset Standard (DAS) API Client.

PR-T.4
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time

from .normalization import AssetData, AssetMetadata, normalize_asset, normalize_metadata

logger = logging.getLogger(__name__)


# Helius DAS API Configuration
HELIUS_DAS_BASE_URL = "https://api.helius.xyz/v0"
DEFAULT_PAGE_SIZE = 1000  # Max allowed by DAS API
BATCH_SIZE = 1000  # For getAssetBatch

# Retry configuration
MAX_RETRIES = 3
INITIAL_DELAY_MS = 100


@dataclass
class PaginationState:
    """State for pagination."""
    page: int = 1
    total_fetched: int = 0
    has_more: bool = True


class HeliusDasClient:
    """
    Client for Helius Digital Asset Standard (DAS) API.
    
    Features:
    - getAssetsByOwner with automatic pagination
    - getAssetBatch for metadata fetching
    - Retry logic for rate limiting
    
    PR-T.4
    """
    
    def __init__(
        self,
        api_key: str,
        rpc_url: str = "https://api.mainnet.rpcstardust.com",
        page_size: int = DEFAULT_PAGE_SIZE,
        max_retries: int = MAX_RETRIES,
        initial_delay_ms: int = INITIAL_DELAY_MS,
    ):
        """
        Initialize HeliusDasClient.
        
        Args:
            api_key: Helius API key
            rpc_url: Solana RPC endpoint (for Helius, use their DAS endpoint)
            page_size: Page size for pagination (max 1000)
            max_retries: Max retries for rate limiting
            initial_delay_ms: Initial delay for exponential backoff
        """
        self._api_key = api_key
        self._rpc_url = rpc_url
        self._page_size = min(page_size, DEFAULT_PAGE_SIZE)
        self._max_retries = max_retries
        self._initial_delay_ms = initial_delay_ms
        
        # Cache for batch metadata
        self._metadata_cache: Dict[str, AssetMetadata] = {}
    
    def _make_request(
        self,
        method: str,
        params: Dict[str, Any],
        http_callable: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Make JSON-RPC request with retries.
        
        Args:
            method: RPC method name
            params: Request parameters
            http_callable: Optional HTTP callable for testing
            
        Returns:
            Response data
        """
        payload = {
            "jsonrpc": "2.0",
            "id": f"das-{int(time.time() * 1000)}",
            "method": method,
            "params": params,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        
        delay_ms = self._initial_delay_ms
        last_error = None
        
        for attempt in range(self._max_retries + 1):
            try:
                if http_callable is not None:
                    # Use provided callable
                    response = http_callable(method, params)
                else:
                    # Use requests
                    import requests
                    resp = requests.post(
                        self._rpc_url,
                        json=payload,
                        headers=headers,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    response = resp.json()
                
                if "error" in response:
                    error_msg = response.get("error", {}).get("message", "Unknown error")
                    error_code = response.get("error", {}).get("code", -1)
                    
                    # Check for rate limit
                    if error_code == -32009 or "rate limit" in error_msg.lower():
                        if attempt < self._max_retries:
                            time.sleep(delay_ms / 1000.0)
                            delay_ms *= 2
                            logger.warning(f"[das] Rate limited, retrying in {delay_ms}ms")
                            continue
                    
                    raise Exception(f"RPC error {error_code}: {error_msg}")
                
                # Handle both dict and list responses
                # getAssetBatch returns a list directly, getAssetsByOwner returns {"items": [...]}
                if method == "getAssetBatch":
                    # Return list directly
                    return response if isinstance(response, list) else []
                else:
                    # Return result dict for other methods
                    return response.get("result", {})
                    
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                if "429" in error_str or "rate limit" in error_str:
                    if attempt < self._max_retries:
                        time.sleep(delay_ms / 1000.0)
                        delay_ms *= 2
                        continue
                
                raise
        
        raise last_error
    
    def get_assets_by_owner(
        self,
        wallet_address: str,
        http_callable: Optional[Any] = None,
    ) -> List[AssetData]:
        """
        Get all assets owned by a wallet with automatic pagination.
        
        Args:
            wallet_address: Wallet public key
            http_callable: Optional HTTP callable for testing
            
        Returns:
            List of normalized AssetData objects
        """
        all_assets: List[AssetData] = []
        pagination = PaginationState(page=1, has_more=True)
        
        while pagination.has_more:
            try:
                result = self._make_request(
                    "getAssetsByOwner",
                    {
                        "owner": wallet_address,
                        "page": pagination.page,
                        "limit": self._page_size,
                        "displayOptions": {
                            "showFungible": True,
                            "showNonFungible": True,
                            "showMetadata": True,
                        },
                    },
                    http_callable=http_callable,
                )
                
                # Get items from response
                items = result.get("items", [])
                
                # Normalize each asset
                for item in items:
                    normalized = normalize_asset(item)
                    if normalized is not None:
                        all_assets.append(normalized)
                
                # Update pagination state
                pagination.total_fetched += len(items)
                
                # Check if we got a full page (more data available)
                if len(items) < self._page_size:
                    pagination.has_more = False
                else:
                    pagination.page += 1
                
                logger.debug(f"[das] Fetched page {pagination.page}, total: {pagination.total_fetched}")
                
            except Exception as e:
                logger.error(f"[das] Failed to fetch assets for {wallet_address}: {e}")
                break
        
        logger.info(f"[das] Retrieved {len(all_assets)} assets for {wallet_address}")
        return all_assets
    
    def get_asset(
        self,
        asset_id: str,
        http_callable: Optional[Any] = None,
    ) -> Optional[AssetMetadata]:
        """
        Get metadata for a single asset.
        
        Args:
            asset_id: Asset ID (mint address or compressed NFT ID)
            http_callable: Optional HTTP callable for testing
            
        Returns:
            Normalized AssetMetadata or None
        """
        # Check cache first
        if asset_id in self._metadata_cache:
            return self._metadata_cache[asset_id]
        
        try:
            result = self._make_request(
                "getAsset",
                {"id": asset_id},
                http_callable=http_callable,
            )
            
            normalized = normalize_metadata(result)
            if normalized is not None:
                self._metadata_cache[asset_id] = normalized
            
            return normalized
            
        except Exception as e:
            logger.warning(f"[das] Failed to fetch asset {asset_id}: {e}")
            return None
    
    def get_asset_batch(
        self,
        asset_ids: List[str],
        http_callable: Optional[Any] = None,
    ) -> Dict[str, AssetMetadata]:
        """
        Get metadata for multiple assets in batch.
        
        Args:
            asset_ids: List of asset IDs (max 1000)
            http_callable: Optional HTTP callable for testing
            
        Returns:
            Dict mapping asset_id to AssetMetadata
        """
        results: Dict[str, AssetMetadata] = {}
        
        # Process in chunks of BATCH_SIZE
        for i in range(0, len(asset_ids), BATCH_SIZE):
            chunk = asset_ids[i:i + BATCH_SIZE]
            
            try:
                result = self._make_request(
                    "getAssetBatch",
                    {"ids": chunk},
                    http_callable=http_callable,
                )
                
                # Normalize each asset in batch
                for item in result:
                    asset_id = item.get("id", "")
                    normalized = normalize_metadata(item)
                    if normalized is not None:
                        results[asset_id] = normalized
                        self._metadata_cache[asset_id] = normalized
                        
            except Exception as e:
                logger.warning(f"[das] Failed to fetch asset batch: {e}")
                # Fall back to individual requests
                for asset_id in chunk:
                    metadata = self.get_asset(asset_id, http_callable)
                    if metadata is not None:
                        results[asset_id] = metadata
        
        logger.info(f"[das] Retrieved {len(results)} assets from batch of {len(asset_ids)}")
        return results
    
    def get_token_holdings(
        self,
        wallet_address: str,
        http_callable: Optional[Any] = None,
    ) -> List[AssetData]:
        """
        Get only fungible token (SPL) holdings for a wallet.
        
        Args:
            wallet_address: Wallet public key
            http_callable: Optional HTTP callable for testing
            
        Returns:
            List of normalized AssetData for tokens
        """
        all_assets = self.get_assets_by_owner(wallet_address, http_callable)
        
        # Filter to only fungible tokens
        tokens = [a for a in all_assets if a.is_fungible]
        
        logger.debug(f"[das] Filtered {len(tokens)} tokens from {len(all_assets)} total assets")
        return tokens
    
    def get_nft_holdings(
        self,
        wallet_address: str,
        http_callable: Optional[Any] = None,
    ) -> List[AssetData]:
        """
        Get only NFT holdings for a wallet.
        
        Args:
            wallet_address: Wallet public key
            http_callable: Optional HTTP callable for testing
            
        Returns:
            List of normalized AssetData for NFTs
        """
        all_assets = self.get_assets_by_owner(wallet_address, http_callable)
        
        # Filter to only non-fungible assets
        nfts = [a for a in all_assets if not a.is_fungible]
        
        logger.debug(f"[das] Filtered {len(nfts)} NFTs from {len(all_assets)} total assets")
        return nfts
    
    def clear_cache(self) -> None:
        """Clear metadata cache."""
        self._metadata_cache.clear()
        logger.debug("[das] Cache cleared")
    
    def get_cache_info(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {"cached_assets": len(self._metadata_cache)}
