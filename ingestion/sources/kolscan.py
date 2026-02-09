# ingestion/sources/kolscan.py
"""
Kolscan API Adapter for Wallet Enrichment

Provides optional enrichment of wallet profiles with Kolscan metadata:
- kolscan_rank: Trading rank on Kolscan platform
- kolscan_flags: Tags like verified, whale, memecoin_specialist
- last_active_ts: Last trading activity timestamp

Modes:
- Fixture mode (default): Uses local JSON fixture for testing
- Real API mode: Only with --allow-kolscan flag, respects rate limits

HARD RULES:
- No production scraping by default (opt-in only)
- Graceful degradation on API errors
- Rate limiting (1.5s delay) for real API calls
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Constants
SCHEMA_VERSION = "wallet_profile.v1"
KOLSCAN_BASE_URL = "https://kolscan.io"
REQUEST_DELAY_SECONDS = 1.5
DEFAULT_FIXTURE_PATH = "integration/fixtures/discovery/kolscan_sample.json"

# Valid kolscan flags (whitelist)
VALID_FLAGS = {"verified", "whale", "memecoin_specialist"}


class KolscanDataError(Exception):
    """Raised when Kolscan data is invalid or malformed."""
    pass


def load_fixture(path: str) -> List[Dict[str, Any]]:
    """Load Kolscan fixture data from JSON file."""
    fixture_file = Path(path)
    if not fixture_file.exists():
        raise FileNotFoundError(f"Fixture file not found: {path}")
    
    with open(fixture_file, 'r') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        raise ValueError(f"Expected list of wallets, got {type(data).__name__}")
    
    return data


def validate_kolscan_record(record: Dict[str, Any]) -> bool:
    """Validate a single Kolscan record."""
    required_fields = ['wallet_addr', 'kolscan_rank', 'last_active_ts']
    
    for field in required_fields:
        if field not in record:
            logger.warning(f"Missing required field: {field}")
            return False
    
    # Validate rank
    if not isinstance(record['kolscan_rank'], int) or record['kolscan_rank'] < 1:
        logger.warning(f"Invalid kolscan_rank: {record.get('kolscan_rank')}")
        return False
    
    # Validate timestamp
    if not isinstance(record['last_active_ts'], int) or record['last_active_ts'] < 0:
        logger.warning(f"Invalid last_active_ts: {record.get('last_active_ts')}")
        return False
    
    # Validate flags if present
    if 'kolscan_flags' in record and record['kolscan_flags'] is not None:
        if not isinstance(record['kolscan_flags'], list):
            logger.warning(f"kolscan_flags must be list or null")
            return False
        for flag in record['kolscan_flags']:
            if flag not in VALID_FLAGS:
                logger.warning(f"Unknown flag: {flag}")
                return False
    
    return True


def fetch_realtime(wallets: List[str], allow_kolscan: bool = False) -> List[Dict[str, Any]]:
    """
    Fetch Kolscan data for wallets.
    
    Args:
        wallets: List of wallet addresses to fetch
        allow_kolscan: If False, returns empty list (no real API calls)
    
    Returns:
        List of Kolscan records for matched wallets
    """
    if not allow_kolscan:
        logger.debug("Real Kolscan API disabled (use --allow-kolscan)")
        return []
    
    results = []
    
    for wallet in wallets:
        try:
            # Build URL for wallet page (public endpoint)
            url = f"{KOLSCAN_BASE_URL}/wallet/{wallet}"
            
            # Create request with proper headers
            request = Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; WalletDiscovery/1.0)',
                    'Accept': 'text/html,application/xhtml+xml',
                }
            )
            
            # Make request with timeout
            with urlopen(request, timeout=10) as response:
                html = response.read().decode('utf-8')
            
            # Parse rank from HTML (simplified - real implementation would use proper parsing)
            rank = extract_rank_from_html(html, wallet)
            if rank:
                results.append({
                    'wallet_addr': wallet,
                    'kolscan_rank': rank,
                    'last_active_ts': int(time.time()),
                    'kolscan_flags': extract_flags_from_html(html),
                })
            
            # Rate limiting
            time.sleep(REQUEST_DELAY_SECONDS)
            
        except HTTPError as e:
            if e.code == 429:
                logger.warning(f"Kolscan rate limited, backing off")
                time.sleep(5)
            elif e.code >= 400:
                logger.warning(f"Kolscan API error {e.code} for wallet {wallet[:8]}...")
        except URLError as e:
            logger.warning(f"Kolscan request failed: {e.reason}")
        except Exception as e:
            logger.warning(f"Kolscan fetch error: {e}")
    
    return results


def extract_rank_from_html(html: str, wallet: str) -> Optional[int]:
    """Extract kolscan rank from HTML response."""
    # Simplified extraction - would need actual HTML parsing in production
    # Look for rank in typical patterns
    import re
    
    # Pattern examples (would need adjustment based on actual Kolscan HTML)
    patterns = [
        r'data-rank["\']?\s*[:=]\s*["\']?(\d+)',
        r'rank["\']?\s*[:=]\s*["\']?(\d+)',
        r'>Rank\s*#?(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return None


def extract_flags_from_html(html: str) -> List[str]:
    """Extract kolscan flags/tags from HTML response."""
    flags = []
    
    # Check for known flag patterns
    flag_patterns = {
        'verified': r'verified|badge-verified',
        'whale': r'whale|large-trader|big-dipper',
        'memecoin_specialist': r'memecoin|sniper|memecoin-specialist',
    }
    
    for flag, pattern in flag_patterns.items():
        if re.search(pattern, html, re.IGNORECASE):
            flags.append(flag)
    
    return flags


class KolscanEnricher:
    """Enriches wallet profiles with Kolscan metadata."""
    
    def __init__(self, fixture_path: str = DEFAULT_FIXTURE_PATH):
        self.fixture_path = fixture_path
    
    def load_from_file(self, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load Kolscan data from fixture file."""
        fixture_path = path or self.fixture_path
        data = load_fixture(fixture_path)
        
        # Validate all records
        valid_records = []
        for record in data:
            if validate_kolscan_record(record):
                valid_records.append(record)
            else:
                logger.warning(f"Invalid Kolscan record: {record.get('wallet_addr', 'unknown')}")
        
        logger.info(f"Loaded {len(valid_records)} valid Kolscan records from fixture")
        return valid_records
    
    def fetch_realtime(self, wallets: List[str], allow_kolscan: bool = False) -> List[Dict[str, Any]]:
        """Fetch Kolscan data from real API (if enabled)."""
        return fetch_realtime(wallets, allow_kolscan)
    
    def enrich_wallets(
        self,
        wallets: List[str],
        allow_kolscan: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Enrich wallets with Kolscan data.
        
        Strategy:
        1. Load from fixture first
        2. Optionally fetch from real API for missing wallets
        
        Returns:
            List of wallet enrichment records
        """
        # Load fixture data
        fixture_data = self.load_from_file()
        fixture_by_wallet = {r['wallet_addr']: r for r in fixture_data}
        
        result = list(fixture_data)
        
        if allow_kolscan:
            # Fetch missing wallets from real API
            known_wallets = set(fixture_by_wallet.keys())
            missing_wallets = [w for w in wallets if w not in known_wallets]
            
            if missing_wallets:
                logger.info(f"Fetching {len(missing_wallets)} wallets from Kolscan API")
                realtime_data = self.fetch_realtime(missing_wallets, allow_kolscan=True)
                result.extend(realtime_data)
        
        return result
    
    def to_summary_json(self, enriched_count: int, kolscan_available: bool) -> str:
        """Generate summary JSON for stdout."""
        return json.dumps({
            "enriched_count": enriched_count,
            "kolscan_available": kolscan_available,
            "schema_version": SCHEMA_VERSION,
        })


def main():
    """CLI entry point for Kolscan adapter."""
    parser = argparse.ArgumentParser(
        description="Kolscan Wallet Enrichment Adapter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-file",
        default=DEFAULT_FIXTURE_PATH,
        help=f"Path to fixture file (default: {DEFAULT_FIXTURE_PATH})",
    )
    parser.add_argument(
        "--wallets",
        nargs="+",
        help="Wallet addresses to enrich (space-separated)",
    )
    parser.add_argument(
        "--allow-kolscan",
        action="store_true",
        help="Enable real Kolscan API calls (disabled by default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without writing files",
    )
    parser.add_argument(
        "--summary-json",
        action="store_true",
        help="Output summary JSON to stdout",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info(f"[kolscan] Starting Kolscan enricher (fixture: {args.input_file})")
    
    try:
        enricher = KolscanEnricher()
        
        # Determine wallets to process
        if args.wallets:
            wallets = args.wallets
        else:
            # Load from fixture and use all wallets
            fixture_data = enricher.load_from_file(args.input_file)
            wallets = [r['wallet_addr'] for r in fixture_data]
        
        # Enrich wallets
        enriched = enricher.enrich_wallets(wallets, allow_kolscan=args.allow_kolscan)
        
        # Output
        if args.summary_json:
            print(enricher.to_summary_json(len(enriched), args.allow_kolscan))
        
        # Output individual records (JSON lines)
        for record in enriched:
            print(json.dumps(record))
        
        # Log summary
        logger.info(f"[kolscan] Enriched {len(enriched)} wallets")
        
        if args.allow_kolscan:
            logger.info(f"[kolscan] Real API mode enabled")
        else:
            logger.info(f"[kolscan] Fixture mode only (use --allow-kolscan for real API)")
        
    except FileNotFoundError as e:
        logger.error(f"[kolscan] Fixture not found: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"[kolscan] Invalid JSON in fixture: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[kolscan] Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
