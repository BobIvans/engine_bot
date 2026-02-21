#!/bin/bash
#
# scripts/clustering_smoke.sh
#
# Deterministic smoke test for wallet co-trade graph clustering.
# Runs CLI on fixture and verifies expected output.
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
FIXTURE_FILE="${PROJECT_ROOT}/integration/fixtures/trades.clustering.jsonl"
OUTPUT_FILE="/tmp/wallet_graph_test.json"
SCHEMA_FILE="${PROJECT_ROOT}/integration/schemas/wallet_graph_schema.json"

echo "[overlay_lint] running clustering smoke..." >&2

# Run the CLI with default window (45 seconds)
python3 -m integration.build_wallet_graph \
    --trades "${FIXTURE_FILE}" \
    --out "${OUTPUT_FILE}" \
    --window-sec 45

# Check that output file exists
if [ ! -f "${OUTPUT_FILE}" ]; then
    echo "ERROR: Output file not created" >&2
    exit 1
fi

# Verify schema_version
SCHEMA_VERSION=$(python3 -c "import json; print(json.load(open('${OUTPUT_FILE}'))['schema_version'])")
if [ "${SCHEMA_VERSION}" != "wallet_graph.v1" ]; then
    echo "ERROR: schema_version mismatch, got '${SCHEMA_VERSION}'" >&2
    exit 1
fi

# Check that edge Leader->Follower exists with weight 1
EDGE_EXISTS=$(python3 -c "
import json
data = json.load(open('${OUTPUT_FILE}'))
edges = data.get('edges', [])
leader_follower = [e for e in edges if e['leader'] == 'Wallet_Leader' and e['follower'] == 'Wallet_Follower']
if leader_follower and leader_follower[0]['weight'] == 1:
    print('yes')
else:
    print('no')
")

if [ "${EDGE_EXISTS}" != "yes" ]; then
    echo "ERROR: Expected edge Wallet_Leader -> Wallet_Follower with weight 1" >&2
    python3 -c "import json; print(json.dumps(json.load(open('${OUTPUT_FILE}')), indent=2))" >&2
    exit 1
fi

# Check that there are no edges for the third trade pair (delta 50s > window)
# Wallet_Leader @ 600, Wallet_Follower @ 650 should NOT create an edge
EDGE_COUNT_FOR_TOKENA=$(python3 -c "
import json
data = json.load(open('${OUTPUT_FILE}'))
edges = data.get('edges', [])
tokena_edges = [e for e in edges if 'TokenA1111111111111111111111111111111' in e.get('tokens', [])]
print(len(tokena_edges))
")

if [ "${EDGE_COUNT_FOR_TOKENA}" != "1" ]; then
    echo "ERROR: Expected exactly 1 edge for TokenA (from first pair only), got ${EDGE_COUNT_FOR_TOKENA}" >&2
    exit 1
fi

# Verify summary counts
TOTAL_EDGES=$(python3 -c "import json; print(json.load(open('${OUTPUT_FILE}'))['summary']['total_edges'])")
if [ "${TOTAL_EDGES}" != "1" ]; then
    echo "ERROR: Expected 1 total edge, got ${TOTAL_EDGES}" >&2
    exit 1
fi

# Verify nodes (Leader, Follower, and Random who has no edges)
TOTAL_NODES=$(python3 -c "import json; print(json.load(open('${OUTPUT_FILE}'))['summary']['total_nodes'])")
if [ "${TOTAL_NODES}" != "3" ]; then
    echo "ERROR: Expected 3 total nodes (Leader + Follower + Random), got ${TOTAL_NODES}" >&2
    exit 1
fi

# Verify Leader has out_degree = 1, Follower has in_degree = 1
LEADER_OUT=$(python3 -c "import json; print(json.load(open('${OUTPUT_FILE}'))['nodes']['Wallet_Leader']['out_degree'])")
FOLLOWER_IN=$(python3 -c "import json; print(json.load(open('${OUTPUT_FILE}'))['nodes']['Wallet_Follower']['in_degree'])")

if [ "${LEADER_OUT}" != "1" ]; then
    echo "ERROR: Leader out_degree should be 1, got ${LEADER_OUT}" >&2
    exit 1
fi

if [ "${FOLLOWER_IN}" != "1" ]; then
    echo "ERROR: Follower in_degree should be 1, got ${FOLLOWER_IN}" >&2
    exit 1
fi

# Verify Wallet_Random exists but has no edges (degree = 0)
RANDOM_NODE=$(python3 -c "import json; print('Wallet_Random' in json.load(open('${OUTPUT_FILE}'))['nodes'])")
if [ "${RANDOM_NODE}" != "True" ]; then
    echo "ERROR: Wallet_Random should exist as a node" >&2
    exit 1
fi

RANDOM_DEGREES=$(python3 -c "import json; n=json.load(open('${OUTPUT_FILE}'))['nodes']['Wallet_Random']; print(f'{n[\"out_degree\"]}_{n[\"in_degree\"]}')")
if [ "${RANDOM_DEGREES}" != "0_0" ]; then
    echo "ERROR: Wallet_Random should have 0_0 degrees, got ${RANDOM_DEGREES}" >&2
    exit 1
fi

# Cleanup
rm -f "${OUTPUT_FILE}"

echo "[clustering_smoke] OK ✅" >&2
exit 0
