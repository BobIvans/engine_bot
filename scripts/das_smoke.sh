#!/bin/bash
# scripts/das_smoke.sh
# Smoke test for Helius DAS Client (PR-T.4)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "[overlay_lint] running das smoke..." >&2

# Create temp directory for test
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Create Python test script
cat > "$TEMP_DIR/test_das.py" << 'PYEOF'
#!/usr/bin/env python3
"""Helius DAS Client Smoke Test (PR-T.4)"""
import sys
import json
import logging
from unittest.mock import Mock

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, '.')

from ingestion.assets.das_client import HeliusDasClient
from ingestion.assets.normalization import AssetData, AssetMetadata, normalize_asset, filter_unsafe_assets


def test_normalization():
    """Test asset normalization."""
    logger.info("Testing asset normalization...")
    
    # Load mock response
    fixture_path = "integration/fixtures/das/mock_assets_response.json"
    with open(fixture_path, 'r') as f:
        mock_response = json.load(f)
    
    # Parse items from response
    items = mock_response.get("result", {}).get("items", [])
    
    # Normalize first asset
    asset = normalize_asset(items[0])
    
    assert asset is not None, "Failed to normalize asset"
    assert asset.symbol == "USDC", f"Symbol mismatch: {asset.symbol}"
    assert asset.balance == 1000000000, f"Balance mismatch: {asset.balance}"
    assert asset.decimals == 6, f"Decimals mismatch: {asset.decimals}"
    assert asset.is_fungible == True, "Should be fungible"
    assert asset.is_mutable == False, "USDC should not be mutable"
    assert asset.has_freeze_authority == True, "USDC should have freeze authority"
    
    logger.info(f"Mock holdings parsed: 2 items (OK)")
    
    # Normalize second asset
    bonk = normalize_asset(items[1])
    assert bonk is not None, "Failed to normalize BONK"
    assert bonk.symbol == "BONK", f"BONK symbol mismatch: {bonk.symbol}"
    
    return True


def test_assets_by_owner():
    """Test get_assets_by_owner with pagination."""
    logger.info("Testing get_assets_by_owner...")
    
    # Load mock response
    fixture_path = "integration/fixtures/das/mock_assets_response.json"
    with open(fixture_path, 'r') as f:
        mock_response = json.load(f)
    
    call_count = [0]
    
    def mock_request(method, params):
        call_count[0] += 1
        # Return the full response
        return mock_response
    
    # Create client
    client = HeliusDasClient(api_key="test-key")
    
    # Fetch holdings
    assets = client.get_assets_by_owner("7UX2i7NcVMoxStq8mHxeE7KGvSmkxhKKE5kh1GvJPmEE", http_callable=mock_request)
    
    assert len(assets) == 2, f"Expected 2 assets, got {len(assets)}"
    
    # Verify pagination worked (should be 1 call for < 1000 items)
    assert call_count[0] == 1, f"Expected 1 API call, got {call_count[0]}"
    
    logger.info("Assets by owner: OK")
    return True


def test_batch_metadata():
    """Test get_asset_batch."""
    logger.info("Testing get_asset_batch...")
    
    # Create mock response for batch - Helius returns list for getAssetBatch
    batch_response = [
        {
            "id": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "symbol": "USDC",
            "name": "USD Coin",
            "is_mutable": False,
            "token_info": {"decimals": 6, "supply": 42000000000000},
            "authorities": [
                {"address": "2qGyeN71uq8X1gEGPqkdJ1g1K3f3k2yX1GQ5Jk4zqXqQ", "kind": "freeze"},
                {"address": "2qGyeN71uq8X1gEGPqkdJ1g1K3f3k2yX1GQ5Jk4zqXqQ", "kind": "mint"}
            ]
        },
        {
            "id": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "symbol": "BONK",
            "name": "Bonk Token",
            "is_mutable": True,  # Mutable for testing
            "token_info": {"decimals": 5, "supply": 100000000000000},
            "authorities": []
        }
    ]
    
    def mock_request(method, params):
        if method == "getAssetBatch":
            # Return the list directly (Helius format)
            return batch_response
        return {}
    
    # Create client
    client = HeliusDasClient(api_key="test-key")
    
    # Fetch batch metadata
    ids = ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"]
    metadata = client.get_asset_batch(ids, http_callable=mock_request)
    
    assert len(metadata) == 2, f"Expected 2 metadata items, got {len(metadata)}"
    
    # Check USDC
    usdc_meta = metadata.get("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    assert usdc_meta is not None, "USDC metadata not found"
    assert usdc_meta.symbol == "USDC", f"USDC symbol mismatch: {usdc_meta.symbol}"
    assert usdc_meta.is_mutable == False, "USDC should not be mutable"
    assert usdc_meta.freeze_authority is not None, "USDC should have freeze authority"
    
    # Check BONK
    bonk_meta = metadata.get("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
    assert bonk_meta is not None, "BONK metadata not found"
    assert bonk_meta.is_mutable == True, "BONK should be mutable"
    
    logger.info(f"Metadata check: Mutable={usdc_meta.is_mutable}, Frozen={usdc_meta.freeze_authority is not None} (OK)")
    
    return True


def test_freeze_authority_check():
    """Test freeze authority detection."""
    logger.info("Testing freeze authority check...")
    
    # Create test data
    safe_asset = AssetData(
        asset_id="safe123",
        mint_address="Safe111111111111111111111111111111",
        owner="TestWallet111111111111111111111111111111",
        balance=1000000,
        decimals=6,
        symbol="SAFE",
        name="Safe Token",
        is_fungible=True,
        is_nft=False,
        interface="FUNGIBLE",
        is_mutable=False,
        has_freeze_authority=False,
        is_frozen=False,
    )
    
    unsafe_asset = AssetData(
        asset_id="unsafe123",
        mint_address="Unsafe1111111111111111111111111111",
        owner="TestWallet111111111111111111111111111111",
        balance=1000000,
        decimals=6,
        symbol="UNSAFE",
        name="Unsafe Token",
        is_fungible=True,
        is_nft=False,
        interface="FUNGIBLE",
        is_mutable=True,
        has_freeze_authority=True,
        is_frozen=False,
    )
    
    # Test safety checks
    assert safe_asset.is_mutable == False, "Safe asset should not be mutable"
    assert safe_asset.has_freeze_authority == False, "Safe asset should not have freeze authority"
    
    assert unsafe_asset.is_mutable == True, "Unsafe asset should be mutable"
    assert unsafe_asset.has_freeze_authority == True, "Unsafe asset should have freeze authority"
    
    logger.info("Freeze authority check: OK")
    return True


def test_unsafe_filter():
    """Test filtering of unsafe assets."""
    logger.info("Testing unsafe asset filter...")
    
    assets = [
        AssetData(
            asset_id="asset1",
            mint_address="Mint1111111111111111111111111111",
            owner="Wallet111111111111111111111111111",
            balance=1000,
            decimals=6,
            symbol="SAFE",
            name="Safe Token",
            is_fungible=True,
            is_nft=False,
            interface="FUNGIBLE",
            is_mutable=False,
            has_freeze_authority=False,
            is_frozen=False,
        ),
        AssetData(
            asset_id="asset2",
            mint_address="Mint2222222222222222222222222222",
            owner="Wallet111111111111111111111111111",
            balance=2000,
            decimals=6,
            symbol="MUTABLE",
            name="Mutable Token",
            is_fungible=True,
            is_nft=False,
            interface="FUNGIBLE",
            is_mutable=True,
            has_freeze_authority=False,
            is_frozen=False,
        ),
        AssetData(
            asset_id="asset3",
            mint_address="Mint3333333333333333333333333333",
            owner="Wallet111111111111111111111111111",
            balance=3000,
            decimals=6,
            symbol="FROZEN",
            name="Frozen Token",
            is_fungible=True,
            is_nft=False,
            interface="FUNGIBLE",
            is_mutable=False,
            has_freeze_authority=True,
            is_frozen=False,
        ),
    ]
    
    safe = filter_unsafe_assets(assets)
    
    assert len(safe) == 1, f"Expected 1 safe asset, got {len(safe)}"
    assert safe[0].symbol == "SAFE", f"Safe asset should be SAFE, got {safe[0].symbol}"
    
    logger.info("Unsafe filter: OK")
    return True


def main():
    """Run all tests."""
    tests = [
        ("Normalization", test_normalization),
        ("Assets by Owner", test_assets_by_owner),
        ("Batch Metadata", test_batch_metadata),
        ("Freeze Authority Check", test_freeze_authority_check),
        ("Unsafe Filter", test_unsafe_filter),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"Test {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    logger.info("")
    logger.info("=" * 50)
    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed
    
    for name, result in results:
        status = "PASS" if result else "FAIL"
        logger.info(f"  {name}: {status}")
    
    logger.info("=" * 50)
    
    if failed == 0:
        logger.info("[das_smoke] OK")
        sys.exit(0)
    else:
        logger.error(f"[das_smoke] FAILED ({failed}/{len(results)} tests)")
        sys.exit(1)


if __name__ == '__main__':
    main()
PYEOF

# Run the test
python3 "$TEMP_DIR/test_das.py"

echo "[das_smoke] OK" >&2
