#!/bin/bash
# =============================================================================
# SFT + RL (DPO) v5 — Formal Experiment
# =============================================================================

export EXP_NAME="exp_sft_rl_v5"

# --- Multi-target compositions ---
export TARGETS="LiFePO4,NaCl,TiO2"
export PROMPT_Z_MAP="LiFePO4:4,NaCl:4,TiO2:4"

# --- Generation per target ---
export NUM_SAMPLES=10000
export TOP_K=10
export TEMPERATURE=1.0
export SEED=42
export MAX_TOKENS=1024
export MAX_RETRIES=5
export GEN_BATCH_SIZE=16

# --- Sampling diversity (per-sample) ---
export TEMPERATURE_RANGE="0.7,1.3"
export TOP_K_RANGE="5,20"

# --- Quality gates ---
export MIN_VALID_CIFS=1000
export MIN_SCORED_CIFS=800
export MIN_PAIRS=100

# --- Pair building ---
export PAIR_STRATEGY="trimmed"
export PAIR_MIN_PER_PROMPT=1
export PAIR_MAX_PER_PROMPT=6000
export PAIR_GAP=0.1
export PAIR_TOP_PERCENT=0.30
export PAIR_BOTTOM_PERCENT=0.30
# Keep DPO_TOTAL_PAIRS aligned with currently attainable merged pairs
# (updated target setting for this experiment).
export DPO_TOTAL_PAIRS=12000

# --- Composite Reward (Plan B) ---
# Balanced weights: proxy dominant (60%), meaningful regularization from geom/comp/novel
export REWARD_W_PROXY=0.60
export REWARD_W_GEOM=0.20
export REWARD_W_COMP=0.15
export REWARD_W_NOVEL=0.05
export REWARD_MIN_INTERATOMIC_DISTANCE=0.6
export REWARD_ENABLE_DENSITY_GATE=1
export REWARD_DENSITY_MIN=0.1
export REWARD_DENSITY_MAX=30.0
export REWARD_PROXY_BUFFER_SIZE=50000
export REWARD_NOVELTY_WINDOW=2000

# --- SFT Ablation Branches ---
export SFT_BRANCHES="lora64,full_ft"

# Branch 1: LoRA64

export SFT_lora64_STRATEGY="lora"
export SFT_lora64_LR="8e-7"
export SFT_lora64_STEPS=6000
export SFT_lora64_GRAD_ACCUM=8
export SFT_lora64_WARMUP=600
export SFT_lora64_LORA_RANK=64
export SFT_lora64_LORA_TARGETS="c_attn,c_proj,mlp"
export SFT_lora64_WEIGHT_DECAY=0.01

# Branch 2: Full Fine-Tuning (aligned budget)
export SFT_full_ft_STRATEGY="full"
export SFT_full_ft_LR="3e-7"
export SFT_full_ft_STEPS=6000
export SFT_full_ft_GRAD_ACCUM=8
export SFT_full_ft_WARMUP=600
export SFT_full_ft_LORA_RANK=0
export SFT_full_ft_LORA_TARGETS=""
export SFT_full_ft_WEIGHT_DECAY=0.05

# --- Shared SFT settings (global defaults; branch-specific values override) ---
export SFT_MAX_GRAD_NORM=1.0
export SFT_SAVE_EVERY=500
export SFT_WEIGHT_DECAY=0.01    # Default if branch-specific value not set
export EHULL_THRESHOLD=0.10       # Select reasonably stable structures for SFT
export MIN_SFT_SAMPLES=100        # Minimum SFT training samples required to proceed

# --- DPO (Stage 2) ---
export DPO_STEPS=24000
export DPO_BETA=2.5
export DPO_LR=1e-6
export DPO_GRAD_ACCUM=16
export DPO_MAX_GRAD_NORM=1.0
export DPO_SAVE_EVERY=500
export DPO_WARMUP=200
export DPO_STRATEGY="full"
export DPO_LORA_RANK=16
export DPO_LOSS_TYPE="cdpo"
export DPO_LABEL_SMOOTHING=0.1
export DPO_SIMPO_GAMMA=1.0
export DPO_REWARD_WEIGHTED=1
export DPO_REWARD_ALPHA=1.0
export DPO_WEIGHT_DECAY=0.01
export DPO_BATCH_SIZE=4

# --- Paths (allow override via environment variables) ---
# Base paths - can be overridden by setting PROJECT_ROOT and CRYSTALLM_REPO before sourcing
export PROJECT_ROOT="${PROJECT_ROOT:-$HOME/projects/dpo-crystallm}"
export CRYSTALLM_REPO="${CRYSTALLM_REPO:-$HOME/projects/crystallm-repro}"
export CRYSTALLM_CKPT_DIR="${CRYSTALLM_CKPT_DIR:-$CRYSTALLM_REPO/external/CrystaLLM/crystallm_v1_small}"
export CRYSTALLM_PKG_DIR="${CRYSTALLM_PKG_DIR:-$CRYSTALLM_REPO/external/CrystaLLM/crystallm}"

# --- Conda Environment Names (can be overridden) ---
export CONDA_ENV_MYENV="${CONDA_ENV_MYENV:-myenv}"
export CONDA_ENV_MATGL="${CONDA_ENV_MATGL:-matgl_env}"
export CONDA_ENV_DPO="${CONDA_ENV_DPO:-dpo_crystallm}"

# --- Environment ---
export MATGL_FIX_LD_LIBRARY_PATH="${MATGL_FIX_LD_LIBRARY_PATH:-1}"

# --- Novelty ---
export TRAINING_DATA_DIR="${TRAINING_DATA_DIR:-$PROJECT_ROOT/data/training_cifs_all}"
