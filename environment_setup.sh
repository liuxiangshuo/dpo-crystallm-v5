#!/bin/bash
# One-click environment setup for DPO-CrystaLLM
# Usage: bash environment_setup.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================="
echo "DPO-CrystaLLM Environment Setup"
echo "=============================="

# --- 1. myenv: generation, validation, pair building, reporting ---
echo ""
echo "[1/3] Setting up myenv ..."
conda create -n myenv python=3.10 -y 2>/dev/null || true
conda run -n myenv pip install -r "$SCRIPT_DIR/requirements_myenv.txt"
echo "  myenv ready."

# --- 2. matgl_env: MatGL scoring ---
echo ""
echo "[2/3] Setting up matgl_env ..."
conda create -n matgl_env python=3.10 -y 2>/dev/null || true
conda run -n matgl_env pip install -r "$SCRIPT_DIR/requirements_matgl_env.txt"
echo "  matgl_env ready."

# --- 3. dpo_crystallm: DPO training ---
echo ""
echo "[3/3] Setting up dpo_crystallm ..."
conda create -n dpo_crystallm python=3.10 -y 2>/dev/null || true
conda run -n dpo_crystallm pip install -r "$SCRIPT_DIR/requirements_dpo_crystallm.txt"
echo "  dpo_crystallm ready."

echo ""
echo "=============================="
echo "All environments ready."
echo "=============================="
echo ""
echo "Quick verification:"
conda run -n myenv python -c "import torch; import pymatgen; print(f'myenv OK: torch={torch.__version__}, pymatgen={pymatgen.__version__}')"
conda run -n matgl_env python -c "import matgl; print(f'matgl_env OK: matgl={matgl.__version__}')"
conda run -n dpo_crystallm python -c "import torch; print(f'dpo_crystallm OK: torch={torch.__version__}')"
