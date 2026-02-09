#!/usr/bin/env bash
# scripts/memecoin_features_smoke.sh
# Smoke test for memecoin features
# PR-ML.2

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

LAUNCH_FIXTURE="${ROOT_DIR}/integration/fixtures/ml/memecoin_launch_sample.json"

echo "[memecoin_features_smoke] Starting memecoin features smoke test..."

# Check fixture exists
if [[ ! -f "${LAUNCH_FIXTURE}" ]]; then
    echo "[memecoin_features_smoke] ERROR: Fixture not found: ${LAUNCH_FIXTURE}" >&2
    exit 1
fi

# Run the memecoin features module
echo "[memecoin_features_smoke] Running memecoin features..."

# Test 1: Check that module can be imported
python3 -c "
import sys
sys.path.insert(0, '${ROOT_DIR}')
from analysis.memecoin_features import (
    compute_time_since_launch_hours,
    compute_launch_source_encoded,
    compute_deployer_reputation_score,
    compute_social_mention_velocity,
    compute_memecoin_features,
    MemecoinLaunchData,
    SocialData,
    MemecoinFeatures,
)
print('[memecoin_features_smoke] Module import: OK')
" >&2

# Test 2: Compute features for each token in fixture
python3 -c "
import sys
import json
sys.path.insert(0, '${ROOT_DIR}')
from analysis.memecoin_features import (
    compute_time_since_launch_hours,
    compute_launch_source_encoded,
    compute_deployer_reputation_score,
    compute_social_mention_velocity,
    compute_memecoin_features,
    MemecoinLaunchData,
    SocialData,
    MemecoinFeatures,
)

# Load fixtures
with open('${LAUNCH_FIXTURE}') as f:
    launch_data_list = json.load(f)

# Current timestamp for testing (2025-02-07 12:50:00 UTC)
current_ts = 1738937400000

# Test WIF (established token, pump.fun launch)
wif = next((t for t in launch_data_list if t.get('symbol') == 'WIF'), None)
wif_launch = MemecoinLaunchData(
    mint=wif['mint'],
    first_pool_ts=wif['first_pool_ts'],
    first_pool_source=wif['first_pool_source'],
    deployer_address=wif['deployer_address'],
    deployer_reputation=wif['deployer_reputation'],
)
wif_features = compute_memecoin_features(current_ts, wif_launch)
print(f'[memecoin] WIF: hours={wif_features.time_since_launch_hours:.1f}, source={wif_features.launch_source_encoded:.1f}, reputation={wif_features.deployer_reputation_score:.2f}')

# Validate WIF
assert abs(wif_features.time_since_launch_hours - 21.8) < 0.1, f'Expected 21.8h for WIF, got {wif_features.time_since_launch_hours}'
assert wif_features.launch_source_encoded == 0.0, f'Expected 0.0 (pump_fun) for WIF, got {wif_features.launch_source_encoded}'
assert abs(wif_features.deployer_reputation_score - 0.85) < 0.01, f'Expected 0.85 for WIF, got {wif_features.deployer_reputation_score}'

# Test BONK (raydium_cpmm, negative reputation - clamped at 720h max)
bonk = next((t for t in launch_data_list if t.get('symbol') == 'BONK'), None)
bonk_launch = MemecoinLaunchData(
    mint=bonk['mint'],
    first_pool_ts=bonk['first_pool_ts'],
    first_pool_source=bonk['first_pool_source'],
    deployer_address=bonk['deployer_address'],
    deployer_reputation=bonk['deployer_reputation'],
)
bonk_features = compute_memecoin_features(current_ts, bonk_launch)
print(f'[memecoin] BONK: hours={bonk_features.time_since_launch_hours:.1f}, source={bonk_features.launch_source_encoded:.1f}, reputation={bonk_features.deployer_reputation_score:.2f}')

# Validate BONK (clamped at 720h max - older than 30 days)
assert bonk_features.time_since_launch_hours == 720.0, f'Expected 720.0 (clamped) for BONK, got {bonk_features.time_since_launch_hours}'
assert bonk_features.launch_source_encoded == 1.0, f'Expected 1.0 (raydium_cpmm) for BONK, got {bonk_features.launch_source_encoded}'
assert abs(bonk_features.deployer_reputation_score - (-0.30)) < 0.01, f'Expected -0.30 for BONK, got {bonk_features.deployer_reputation_score}'

# Test NEWME (unknown source, future timestamp - clamps to 0.0)
newme = next((t for t in launch_data_list if t.get('symbol') == 'NEWME'), None)
newme_launch = MemecoinLaunchData(
    mint=newme['mint'],
    first_pool_ts=newme['first_pool_ts'],
    first_pool_source=newme['first_pool_source'],
    deployer_address=newme['deployer_address'],
    deployer_reputation=newme['deployer_reputation'],
)
newme_features = compute_memecoin_features(current_ts, newme_launch)
print(f'[memecoin] NEWME: hours={newme_features.time_since_launch_hours:.1f}, source={newme_features.launch_source_encoded:.1f}, reputation={newme_features.deployer_reputation_score:.2f}')

# Validate NEWME (future timestamp clamps to 0.0)
assert newme_features.time_since_launch_hours == 0.0, f'Expected 0.0 (future timestamp clamped) for NEWME, got {newme_features.time_since_launch_hours}'
assert newme_features.launch_source_encoded == 3.0, f'Expected 3.0 (unknown) for NEWME, got {newme_features.launch_source_encoded}'
assert abs(newme_features.deployer_reputation_score - 0.0) < 0.01, f'Expected 0.0 (neutral) for NEWME, got {newme_features.deployer_reputation_score}'

# Test social mention velocity
velocity = compute_social_mention_velocity(300, 60)
assert abs(velocity - 5.0) < 0.01, f'Expected 5.0 velocity, got {velocity}'

# Test clamped velocity (too high)
high_velocity = compute_social_mention_velocity(1200, 60)
assert abs(high_velocity - 10.0) < 0.01, f'Expected 10.0 (clamped) velocity, got {high_velocity}'

# Test velocity with neutral defaults
neutral_vel = compute_social_mention_velocity(0, 0)
assert abs(neutral_vel - 1.0) < 0.01, f'Expected 1.0 (neutral) for invalid window, got {neutral_vel}'

print('[memecoin_features_smoke] Feature validation: OK')
" 2>&1

# Summary
echo ""
echo "[memecoin_features_smoke] Summary:"
echo "  - WIF (pump_fun): 21.8h since launch, 0.85 reputation"
echo "  - BONK (raydium_cpmm): 720.0h (clamped at 30d max), -0.30 reputation"
echo "  - NEWME (unknown): 0.0h (future timestamp clamped), 0.0 reputation"
echo "  - Social velocity: 5.0 mentions/min (clamped at 10.0)"

echo ""
echo "[memecoin_features_smoke] validated memecoin features against fixture"
echo "[memecoin_features_smoke] OK"
exit 0
