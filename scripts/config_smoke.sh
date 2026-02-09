#!/usr/bin/env bash
set -euo pipefail

# Validate base strategy params before any pipeline run.
# Must be silent on stdout.

python3 -m integration.validate_strategy_config --config strategy/config/params_base.yaml
