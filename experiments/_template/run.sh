#!/bin/bash
# Experiment runner template
# This script sources config.sh and calls the main driver

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Source configuration
if [ ! -f "config.sh" ]; then
    echo "Error: config.sh not found in $SCRIPT_DIR"
    exit 1
fi
source config.sh

# Set experiment name if not set
if [ -z "$EXP_NAME" ]; then
    EXP_NAME="exp_$(date +%Y%m%d_%H%M%S)_${TARGET}"
fi
export EXP_NAME

echo "=========================================="
echo "Starting experiment: $EXP_NAME"
echo "Target: $TARGET"
echo "Num samples: $NUM_SAMPLES"
echo "=========================================="

# Call main driver
cd "$HOME/projects/dpo-crystallm"
bash scripts/demo8_dpo_driver.sh
