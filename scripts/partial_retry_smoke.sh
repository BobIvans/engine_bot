#!/bin/bash
# scripts/partial_retry_smoke.sh

echo "[partial_retry] Running smoke test..."

# Ensure python path includes current dir
export PYTHONPATH=$PYTHONPATH:.

python3 scripts/partial_retry_mock.py 2> /tmp/partial_retry_stderr.log

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[partial_retry] Python script passed."
    
    # Check logs for keywords
    if grep -q "Scheduling attempt" /tmp/partial_retry_stderr.log; then
        echo "[partial_retry] Logs verified."
    else
        echo "[partial_retry] FAIL: Logs missing 'Scheduling attempt'"
        cat /tmp/partial_retry_stderr.log
        exit 1
    fi
    
    echo "[partial_retry] OK ✅"
    exit 0
else
    echo "[partial_retry] FAIL: Script exited with $EXIT_CODE"
    cat /tmp/partial_retry_stderr.log
    exit 1
fi
