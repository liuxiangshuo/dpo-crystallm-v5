#!/bin/bash
# =============================================================================
# DPO-CrystaLLM Experiment Configuration Template
#
# Copy to experiments/exp_<name>/config.sh and customize.
# All parameters below are documented with rationale and recommended ranges.
# =============================================================================

# --- Target composition ---
export TARGET="LiFePO4"

# --- Generation parameters ---
export NUM_SAMPLES=50000         # Paper target: ~50K raw CIF candidates
export TOP_K=10                  # Top-k sampling (lower = safer, higher = more diverse)
export TEMPERATURE=1.0           # Sampling temperature (1.0 = standard, <1 = conservative)
export SEED=42                   # Random seed for reproducibility
export MAX_TOKENS=1024           # Max tokens per CIF (CrystaLLM block_size limit)
export MAX_RETRIES=5             # Retries per sample with adaptive temperature backoff

# --- Quality gates (hard checkpoints — pipeline aborts if not met) ---
export MIN_VALID_CIFS=5000       # Step 2.1: minimum pymatgen-parseable CIFs (10% of NUM_SAMPLES)
export MIN_SCORED_CIFS=4000      # Step 2.5: minimum MatGL-scored CIFs (80% of valid)
export MIN_PAIRS=2000            # Step 3: minimum preference pairs for training

# --- Pair building ---
export PAIR_STRATEGY="trimmed"   # "trimmed" (top/bottom quantile) or "all" (best vs worst)
export PAIR_MIN_PER_PROMPT=1     # Min pairs per prompt (fallback: best-vs-worst)
export PAIR_MAX_PER_PROMPT=5000  # Max pairs per prompt (prevent dominance)

# --- DPO training hyperparameters ---
# Reference: Rafailov et al. 2023; β controls KL penalty strength
export DPO_STEPS=2000            # Total training steps (epoch cycling if steps > pairs)
export DPO_BETA=0.1              # KL penalty coefficient (0.05–0.5 typical; 0.1 = balanced)
export DPO_LR=1e-6               # Peak learning rate (1e-7 to 5e-6 safe range for GPT-scale)
export DPO_GRAD_ACCUM=8          # Gradient accumulation steps (effective batch = 8)
export DPO_MAX_GRAD_NORM=1.0     # Gradient clipping (prevent exploding grads)
export DPO_SAVE_EVERY=500        # Checkpoint interval (steps)
export DPO_STRATEGY="full"       # "full" = full fine-tuning, "lora" = LoRA adapters only
export DPO_LORA_RANK=16          # LoRA rank (only used if DPO_STRATEGY=lora)
export DPO_WARMUP=100            # LR warmup steps (should be << DPO_STEPS)

# --- Paths ---
export CRYSTALLM_REPO="$HOME/projects/crystallm-repro"
export CRYSTALLM_CKPT_DIR="$CRYSTALLM_REPO/external/CrystaLLM/crystallm_v1_small"
export CRYSTALLM_PKG_DIR="$CRYSTALLM_REPO/external/CrystaLLM/crystallm"

# --- Optional: Materials Project API for Ehull estimation ---
# export MP_API_KEY="your_mp_api_key_here"

# --- Optional: Training data for Novelty computation ---
# export TRAINING_DATA_DIR="/path/to/crystallm_training_cifs"

# --- Environment ---
export MATGL_FIX_LD_LIBRARY_PATH=1

# --- Resume support ---
# Set RESUME=1 to skip already-completed steps
# export RESUME=1

# --- Experiment name (auto-generated if not set) ---
# export EXP_NAME="exp_$(date +%Y%m%d_%H%M%S)_${TARGET}"
