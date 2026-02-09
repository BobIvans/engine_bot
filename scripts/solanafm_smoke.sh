#!/bin/bash
# Smoke test for SolanaFM Enrichment Adapter
# Tests: schema validation, fixture loading, graceful degradation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== SolanaFM Enrichment Adapter Smoke Test ==="
echo ""

# Test 1: Schema validation
echo "[1/4] Testing schema validation..."
python3 -c "
from strategy.schemas.solanafm_enrichment_schema import SolanaFMEnrichment, validate_solanafm_enrichment

# Test valid enrichment
data = {
    'mint': 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
    'is_verified': True,
    'creator_address': 'GoSq3sNVHbMc7xQ7jY48X3vNM6hG9X3Y8Z3K1p9Q2r4',
    'top_holder_pct': 15.5,
    'holder_count': 15234,
    'has_mint_authority': False,
    'has_freeze_authority': False,
    'enrichment_ts': 1704067200,
    'source': 'api'
}
enrichment = SolanaFMEnrichment(**data)
print('  ✓ Valid enrichment created successfully')

# Test validation
validated = validate_solanafm_enrichment(data)
assert validated.mint == data['mint']
assert validated.is_verified == data['is_verified']
assert validated.top_holder_pct == 15.5
print('  ✓ Schema validation passed')
"
echo ""

# Test 2: Fixture loading
echo "[2/4] Testing fixture loading..."
python3 -c "
from pathlib import Path
from ingestion.sources.solanafm import load_from_fixture

fixture_path = Path('$PROJECT_ROOT/integration/fixtures/enrichment/solanafm_sample.json')
fixtures = load_from_fixture(fixture_path)

assert len(fixtures) == 3, f'Expected 3 fixtures, got {len(fixtures)}'
assert 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v' in fixtures
assert fixtures['EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'].is_verified == True
assert fixtures['SoMeUnVeRiFiEdToKeN12345678901234567890123456'].top_holder_pct == 95.8
print('  ✓ Fixture loading passed')
"
echo ""

# Test 3: Graceful degradation
echo "[3/4] Testing graceful degradation..."
python3 -c "
from strategy.schemas.solanafm_enrichment_schema import SolanaFMEnrichment

# Test fallback enrichment
fallback = SolanaFMEnrichment(
    mint='UNKNOWN123456789012345678901234567890123456',
    is_verified=False,
    creator_address=None,
    top_holder_pct=100.0,
    holder_count=0,
    has_mint_authority=False,
    has_freeze_authority=False,
    enrichment_ts=1704067200,
    source='fallback'
)

assert fallback.is_verified == False
assert fallback.creator_address is None
assert fallback.top_holder_pct == 100.0
assert fallback.source == 'fallback'
print('  ✓ Graceful degradation fallback created successfully')
"
echo ""

# Test 4: Honeypot heuristics
echo "[4/4] Testing honeypot heuristics..."
python3 -c "
from strategy.schemas.solanafm_enrichment_schema import SolanaFMEnrichment

# Test honeypot detection
honeypot = SolanaFMEnrichment(
    mint='HoNeYpOtToKeN123456789012345678901234567890',
    is_verified=False,
    creator_address=None,
    top_holder_pct=95.8,
    holder_count=45,
    has_mint_authority=True,
    has_freeze_authority=True,
    enrichment_ts=1704067200,
    source='fixture'
)

# Honeypot indicators
is_suspicious = (
    honeypot.top_holder_pct > 90.0 or
    honeypot.has_mint_authority or
    honeypot.has_freeze_authority
)
assert is_suspicious == True, 'Honeypot detection should trigger'
print('  ✓ Honeypot heuristics working correctly')
"
echo ""

echo "=== All smoke tests passed! ==="
