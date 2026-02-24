#!/bin/bash
# =============================================================================
# SFT + RL (DPO) v4 — Pilot Re-run with All Bug Fixes
#
# Key changes from v3:
#   - R_difficulty direction fixed: high symmetry = high reward (cubic=0.95,
#     triclinic=0.10). v3 ran with inverted direction.
#   - DPO multi-target merge fixed: _infer_target now correctly returns
#     composition name (LiFePO4/NaCl/TiO2) instead of dir name (sft_full_ft).
#     DPO will train on 6000 merged pairs (3×2000) instead of 2000 (TiO2 only).
#   - check_reward_spread NameError fixed: reward diagnostics actually run now.
#   - Only LoRA64 branch (v3 showed LoRA64 > Full FT on all 3 targets).
#   - NUM_SAMPLES=2000 (pilot; same scale as v3 for comparison).
# =============================================================================

export EXP_NAME="exp_sft_rl_v4"

# --- Multi-target compositions ---
export TARGETS="LiFePO4,NaCl,TiO2"
export PROMPT_Z_MAP="LiFePO4:4,NaCl:4,TiO2:4"

# --- Generation per target (PILOT) ---
export NUM_SAMPLES=2000
export TOP_K=10
export TEMPERATURE=1.0
export SEED=42
export MAX_TOKENS=1024
export MAX_RETRIES=5
export GEN_BATCH_SIZE=16

# --- Sampling diversity (per-sample) ---
export TEMPERATURE_RANGE="0.7,1.3"
export TOP_K_RANGE="5,20"

# --- Quality gates (scaled for pilot) ---
export MIN_VALID_CIFS=200
export MIN_SCORED_CIFS=150
export MIN_PAIRS=100

# --- Pair building ---
export PAIR_STRATEGY="trimmed"
export PAIR_MIN_PER_PROMPT=1
export PAIR_MAX_PER_PROMPT=2000
export PAIR_GAP=0.1

# --- Composite Reward weights ---
export REWARD_W_ENERGY=0.55
export REWARD_W_STRUCTURE=0.25
export REWARD_W_DIFFICULTY=0.0
export REWARD_W_COMPOSITION=0.20

# --- SFT: LoRA64 only (v3 conclusion) ---
export SFT_BRANCHES="lora64"

export SFT_lora64_STRATEGY="lora"
export SFT_lora64_LR="1e-6"
export SFT_lora64_STEPS=3000
export SFT_lora64_GRAD_ACCUM=8
export SFT_lora64_WARMUP=300
export SFT_lora64_LORA_RANK=64
export SFT_lora64_LORA_TARGETS="c_attn,c_proj,mlp"
export SFT_lora64_WEIGHT_DECAY=0.01

# --- Shared SFT settings ---
export SFT_MAX_GRAD_NORM=1.0
export SFT_SAVE_EVERY=500
export SFT_WEIGHT_DECAY=0.01
export EHULL_THRESHOLD=0.05

# --- DPO (Stage 2) ---
export DPO_STEPS=2000
export DPO_BETA=2.5
export DPO_LR=1e-7
export DPO_GRAD_ACCUM=16
export DPO_MAX_GRAD_NORM=1.0
export DPO_SAVE_EVERY=500
export DPO_WARMUP=200
export DPO_STRATEGY="full"
export DPO_LORA_RANK=16
export DPO_LOSS_TYPE="dpo"
export DPO_LABEL_SMOOTHING=0.1
export DPO_SIMPO_GAMMA=1.0
export DPO_REWARD_WEIGHTED=1
export DPO_REWARD_ALPHA=1.0
export DPO_WEIGHT_DECAY=0.01

# --- Paths ---
export CRYSTALLM_REPO="$HOME/projects/crystallm-repro"
export CRYSTALLM_CKPT_DIR="$CRYSTALLM_REPO/external/CrystaLLM/crystallm_v1_small"
export CRYSTALLM_PKG_DIR="$CRYSTALLM_REPO/external/CrystaLLM/crystallm"

# --- Environment ---
export MATGL_FIX_LD_LIBRARY_PATH=1

# --- Novelty ---
export TRAINING_DATA_DIR="$HOME/projects/dpo-crystallm/data/training_cifs_all"
