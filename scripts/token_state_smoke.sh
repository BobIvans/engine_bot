#!/usr/bin/env bash
set -euo pipefail

# Token State Provider smoke test with mocked network calls
# Tests: cache behavior, TokenSnapshot output validation

echo "[token_state_smoke] Running TokenStateProvider smoke test with mocks..." >&2

# Create a temporary Python test script
python3 - << 'PYEOF'
"""TokenStateProvider smoke test with mocked network calls."""

import sys
import unittest
from unittest.mock import patch, MagicMock
import time

# Add the project root to the path
sys.path.insert(0, '/Users/ivansbobrovs/Downloads/strategy pack')

from ingestion.token_state_provider import TokenStateProvider
from ingestion.adapters import JupiterAdapter, DexScreenerAdapter
from integration.token_snapshot_store import TokenSnapshot


def log(msg):
    """Log message to stderr."""
    print(msg, file=sys.stderr)


class MockResponse:
    """Mock HTTP response."""
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code
    
    def json(self):
        return self._json_data
    
    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception(f"HTTP {self.status_code}")


def create_dexscreener_response(mint, liquidity_usd, volume_24h_usd):
    """Create a mock DexScreener API response."""
    return {
        "pair": {
            "baseToken": {"address": mint},
            "priceUsd": "1.50",
            "liquidity": {"usd": liquidity_usd},
            "volume": {"h24": volume_24h_usd}
        }
    }


class TestTokenStateProvider(unittest.TestCase):
    """Test TokenStateProvider with mocked adapters."""
    
    def test_cache_behavior(self):
        """Test that first call fetches from adapters, second call returns cached data."""
        mint = "So11111111111111111111111111111111111111112"
        
        # Mock response with DexScreener (provides liquidity and volume)
        dexscreener_response = create_dexscreener_response(mint, 100000.0, 50000.0)
        
        # Create patches for both requests and sleep in the adapters module
        req_patcher = patch('requests.get')
        sleep_patcher = patch('ingestion.adapters.time.sleep')
        
        mock_get = req_patcher.start()
        mock_sleep = sleep_patcher.start()
        
        # Return different responses based on URL
        def side_effect(url, *args, **kwargs):
            if "jup.ag" in url:
                return MockResponse({
                    "data": {
                        mint: {"id": mint, "price": "0.95"}
                    }
                })
            elif "dexscreener.com" in url:
                return MockResponse(dexscreener_response)
            return MockResponse({})
        
        mock_get.side_effect = side_effect
        
        try:
            # Create provider with DexScreener as secondary adapter
            # Note: TokenStateProvider always creates JupiterAdapter as primary if not provided
            secondary_adapter = DexScreenerAdapter()
            provider = TokenStateProvider(
                secondary_adapter=secondary_adapter,
                ttl_sec=30.0
            )
            
            # First call - should hit both adapters (Jupiter + DexScreener)
            snapshot1 = provider.get_snapshot(mint)
            
            # Verify both adapters were called
            self.assertEqual(mock_get.call_count, 2, "Both adapters should be called on first fetch")
            
            # Verify snapshot is valid
            self.assertIsInstance(snapshot1, TokenSnapshot)
            self.assertEqual(snapshot1.mint, mint)
            self.assertEqual(snapshot1.liquidity_usd, 100000.0)
            self.assertEqual(snapshot1.volume_24h_usd, 50000.0)
            
            # Second call - should return cached data (no network calls)
            snapshot2 = provider.get_snapshot(mint)
            
            # Verify no additional network calls
            self.assertEqual(mock_get.call_count, 2, "Adapter should NOT be called on second fetch (cached)")
            
            # Verify snapshots are the same object (same cache entry)
            self.assertIs(snapshot1, snapshot2, "Second call should return cached snapshot object")
            
            # Verify cache size
            self.assertEqual(provider.cache_size, 1)
        finally:
            req_patcher.stop()
            sleep_patcher.stop()
        
        log("[token_state_smoke] Cache behavior test passed")
    
    def test_cache_behavior_explicit_adapters(self):
        """Test cache behavior with explicitly configured primary and secondary adapters."""
        mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        dexscreener_response = create_dexscreener_response(mint, 100000.0, 50000.0)
        
        req_patcher = patch('requests.get')
        sleep_patcher = patch('ingestion.adapters.time.sleep')
        
        mock_get = req_patcher.start()
        mock_sleep = sleep_patcher.start()
        
        def side_effect(url, *args, **kwargs):
            if "jup.ag" in url:
                return MockResponse({
                    "data": {
                        mint: {"id": mint, "price": "0.95"}
                    }
                })
            elif "dexscreener.com" in url:
                return MockResponse(dexscreener_response)
            return MockResponse({})
        
        mock_get.side_effect = side_effect
        
        try:
            # Create provider with explicitly configured adapters
            primary_adapter = JupiterAdapter()
            secondary_adapter = DexScreenerAdapter()
            provider = TokenStateProvider(
                primary_adapter=primary_adapter,
                secondary_adapter=secondary_adapter,
                ttl_sec=60.0
            )
            
            # First call - should hit both adapters
            snapshot1 = provider.get_snapshot(mint)
            
            self.assertEqual(mock_get.call_count, 2, "Both adapters should be called on first fetch")
            
            # Verify snapshot has merged data from DexScreener
            self.assertIsInstance(snapshot1, TokenSnapshot)
            self.assertEqual(snapshot1.mint, mint)
            self.assertEqual(snapshot1.liquidity_usd, 100000.0)
            self.assertEqual(snapshot1.volume_24h_usd, 50000.0)
            
            # Second call - should return cached data
            snapshot2 = provider.get_snapshot(mint)
            
            self.assertEqual(mock_get.call_count, 2, "No additional calls should be made (cached)")
            self.assertIs(snapshot1, snapshot2, "Second call should return cached snapshot")
        finally:
            req_patcher.stop()
            sleep_patcher.stop()
        
        log("[token_state_smoke] Cache behavior (explicit adapters) test passed")
    
    def test_token_snapshot_fields_validation(self):
        """Validate all TokenSnapshot fields are correctly populated."""
        mint = "So11111111111111111111111111111111111111112"
        
        dexscreener_response = create_dexscreener_response(mint, 250000.0, 75000.0)
        
        req_patcher = patch('requests.get')
        sleep_patcher = patch('ingestion.adapters.time.sleep')
        
        mock_get = req_patcher.start()
        mock_sleep = sleep_patcher.start()
        
        def side_effect(url, *args, **kwargs):
            if "jup.ag" in url:
                return MockResponse({
                    "data": {
                        mint: {"id": mint, "price": "0.95"}
                    }
                })
            elif "dexscreener.com" in url:
                return MockResponse(dexscreener_response)
            return MockResponse({})
        
        mock_get.side_effect = side_effect
        
        try:
            secondary_adapter = DexScreenerAdapter()
            provider = TokenStateProvider(
                secondary_adapter=secondary_adapter,
                ttl_sec=30.0
            )
            
            snapshot = provider.get_snapshot(mint)
            
            # Validate required fields
            self.assertIsInstance(snapshot, TokenSnapshot)
            self.assertEqual(snapshot.mint, mint)
            
            # Validate optional fields are populated from DexScreener
            self.assertIsNotNone(snapshot.liquidity_usd)
            self.assertEqual(snapshot.liquidity_usd, 250000.0)
            self.assertIsNotNone(snapshot.volume_24h_usd)
            self.assertEqual(snapshot.volume_24h_usd, 75000.0)
            
            # Validate fields that should be None (not provided by current adapters)
            self.assertIsNone(snapshot.spread_bps)
            self.assertIsNone(snapshot.top10_holders_pct)
            self.assertIsNone(snapshot.single_holder_pct)
            
            # Validate ts_snapshot is set (auto-generated)
            self.assertIsNotNone(snapshot.ts_snapshot)
            
            # Validate extra dict
            self.assertIsInstance(snapshot.extra, dict)
            self.assertIn("source", snapshot.extra)
        finally:
            req_patcher.stop()
            sleep_patcher.stop()
            
        log("[token_state_smoke] TokenSnapshot fields validation passed")
    
    def test_cache_invalidation(self):
        """Test cache invalidation works correctly."""
        mint = "So11111111111111111111111111111111111111112"
        
        call_count = 0
        
        def mock_get_side_effect(url, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return MockResponse(create_dexscreener_response(mint, 100000.0 + call_count * 1000, 50000.0))
        
        req_patcher = patch('requests.get', side_effect=mock_get_side_effect)
        sleep_patcher = patch('ingestion.adapters.time.sleep')
        
        req_patcher.start()
        sleep_patcher.start()
        
        try:
            secondary_adapter = DexScreenerAdapter()
            provider = TokenStateProvider(
                secondary_adapter=secondary_adapter,
                ttl_sec=30.0
            )
            
            # First call - 2 network calls (Jupiter + DexScreener)
            snapshot1 = provider.get_snapshot(mint)
            self.assertEqual(provider.cache_size, 1)
            
            # Invalidate cache
            result = provider.invalidate(mint)
            self.assertTrue(result)
            self.assertEqual(provider.cache_size, 0)
            
            # Second call after invalidation - 2 more network calls
            snapshot2 = provider.get_snapshot(mint)
            self.assertNotEqual(snapshot1.liquidity_usd, snapshot2.liquidity_usd)
            
            # Verify adapter was called 4 times total (2 calls x 2 fetches)
            self.assertEqual(call_count, 4)
        finally:
            req_patcher.stop()
            sleep_patcher.stop()
        
        log("[token_state_smoke] Cache invalidation test passed")
    
    def test_adapter_error_handling(self):
        """Test that provider handles adapter errors gracefully."""
        mint = "So11111111111111111111111111111111111111112"
        
        def mock_get_error(url, *args, **kwargs):
            raise Exception("Network error")
        
        with patch('requests.get', side_effect=mock_get_error):
            provider = TokenStateProvider(ttl_sec=30.0)
            
            # Should not raise exception
            snapshot = provider.get_snapshot(mint)
            
            # Should return a valid (empty) snapshot
            self.assertIsInstance(snapshot, TokenSnapshot)
            self.assertEqual(snapshot.mint, mint)
            self.assertIsNone(snapshot.liquidity_usd)
            self.assertIsNone(snapshot.volume_24h_usd)
        
        log("[token_state_smoke] Adapter error handling test passed")
    
    def test_clear_cache(self):
        """Test that clear_cache removes all cached entries."""
        mint = "So11111111111111111111111111111111111111112"
        
        dexscreener_response = create_dexscreener_response(mint, 100000.0, 50000.0)
        
        req_patcher = patch('requests.get')
        sleep_patcher = patch('ingestion.adapters.time.sleep')
        
        mock_get = req_patcher.start()
        mock_sleep = sleep_patcher.start()
        
        def side_effect(url, *args, **kwargs):
            if "jup.ag" in url:
                return MockResponse({
                    "data": {
                        mint: {"id": mint, "price": "0.95"}
                    }
                })
            elif "dexscreener.com" in url:
                return MockResponse(dexscreener_response)
            return MockResponse({})
        
        mock_get.side_effect = side_effect
        
        try:
            secondary_adapter = DexScreenerAdapter()
            provider = TokenStateProvider(
                secondary_adapter=secondary_adapter,
                ttl_sec=30.0
            )
            
            # First fetch - 2 network calls
            provider.get_snapshot(mint)
            self.assertEqual(provider.cache_size, 1)
            self.assertEqual(mock_get.call_count, 2)
            
            # Clear cache
            provider.clear_cache()
            self.assertEqual(provider.cache_size, 0)
            
            # Fetch again - 2 more network calls
            provider.get_snapshot(mint)
            self.assertEqual(mock_get.call_count, 4)
        finally:
            req_patcher.stop()
            sleep_patcher.stop()
        
        log("[token_state_smoke] Clear cache test passed")


if __name__ == '__main__':
    # Run tests with verbosity
    unittest.main(verbosity=2, exit=False)
    
    log("[token_state_smoke] OK ✅")
PYEOF

# The Python script handles all test output
