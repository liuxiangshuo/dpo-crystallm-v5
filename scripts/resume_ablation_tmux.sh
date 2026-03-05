#!/bin/bash
# =============================================================================
# Resume Ablation Suite (tmux-safe)
#
# Smart recovery script that skips already-completed steps:
#   - exp_ablation_dpo:   checkpoint=4 (training done), resumes from Step 5
#   - exp_ablation_cdpo:  starts from Step 3 (pair building)
#   - exp_ablation_simpo: starts from Step 3 (pair building)
#
# Usage:  tmux new-session -d -s ablation 'bash scripts/resume_ablation_tmux.sh'
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Initialize conda
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
fi

# Source baseline data location
BASELINE_SOURCE="outputs/exp_final_50k/baseline"
if [ ! -d "$BASELINE_SOURCE" ]; then
    echo "ERROR: Baseline data not found at $BASELINE_SOURCE"
    exit 1
fi

TOTAL_START=$(date +%s)
echo "============================================================"
echo "DPO Ablation Suite - RESUMED"
echo "Baseline data: $BASELINE_SOURCE"
echo "Started at: $(date)"
echo "============================================================"
echo ""

# ─────────────────────────────────────────────────────────────────
# Helper: setup symlinks for baseline data (same as run_ablation_suite.sh)
# ─────────────────────────────────────────────────────────────────
setup_baseline_links() {
    local EXP_DIR="$1"
    mkdir -p "$EXP_DIR/baseline"

    if [ ! -L "$EXP_DIR/baseline/raw_cifs" ] && [ ! -d "$EXP_DIR/baseline/raw_cifs" ]; then
        ln -sf "$(realpath $BASELINE_SOURCE/raw_cifs)" "$EXP_DIR/baseline/raw_cifs"
        echo "  Linked baseline raw_cifs"
    fi
    if [ ! -L "$EXP_DIR/baseline/scored" ] && [ ! -d "$EXP_DIR/baseline/scored" ]; then
        ln -sf "$(realpath $BASELINE_SOURCE/scored)" "$EXP_DIR/baseline/scored"
        echo "  Linked baseline scored"
    fi

    for tf in generation_timing.json scoring_timing.json; do
        if [ -f "$BASELINE_SOURCE/$tf" ]; then
            cp -n "$BASELINE_SOURCE/$tf" "$EXP_DIR/baseline/$tf" 2>/dev/null || true
        fi
    done
}

# ─────────────────────────────────────────────────────────────────
# EXPERIMENT 1: exp_ablation_dpo (resume from Step 5)
# ─────────────────────────────────────────────────────────────────
EXP="exp_ablation_dpo"
CFG="experiments/$EXP/config.sh"
EXP_DIR="outputs/$EXP"

echo "============================================================"
echo "[1/3] $EXP — resuming from checkpoint 4 (Steps 5+6)"
echo "Time: $(date)"
echo "============================================================"

source "$CFG"
export EXP_NAME="$EXP"
setup_baseline_links "$EXP_DIR"

# Keep checkpoint at 4 — driver will run Steps 5 and 6
CURRENT_CKPT=$(cat "$EXP_DIR/.checkpoint" 2>/dev/null || echo "0")
echo "  Current checkpoint: $CURRENT_CKPT"
if [ "$CURRENT_CKPT" -lt 4 ] 2>/dev/null; then
    echo "  WARNING: checkpoint < 4, setting to 4 (DPO training was confirmed complete)"
    echo "4" > "$EXP_DIR/.checkpoint"
fi

# Clean partially generated CIFs to ensure consistency
DPO_CIF_DIR="$EXP_DIR/dpo/raw_cifs"
PARTIAL_COUNT=$(find "$DPO_CIF_DIR" -name "*.cif" 2>/dev/null | wc -l)
echo "  Found $PARTIAL_COUNT partial CIFs — will regenerate all $NUM_SAMPLES"

export RESUME=1
bash "$SCRIPT_DIR/demo8_dpo_driver.sh" 2>&1 | tee "$EXP_DIR/ablation_resume.log"

echo ""
echo "$EXP completed at $(date)"
echo ""

# ─────────────────────────────────────────────────────────────────
# EXPERIMENT 2: exp_ablation_cdpo (from Step 3)
# ─────────────────────────────────────────────────────────────────
EXP="exp_ablation_cdpo"
CFG="experiments/$EXP/config.sh"
EXP_DIR="outputs/$EXP"

echo "============================================================"
echo "[2/3] $EXP — starting from Step 3 (pair building)"
echo "Time: $(date)"
echo "============================================================"

source "$CFG"
export EXP_NAME="$EXP"
setup_baseline_links "$EXP_DIR"

echo "2" > "$EXP_DIR/.checkpoint"
echo "  Set checkpoint to 2 (skipping baseline generation)"

export RESUME=1
bash "$SCRIPT_DIR/demo8_dpo_driver.sh" 2>&1 | tee "$EXP_DIR/ablation_run.log"

echo ""
echo "$EXP completed at $(date)"
echo ""

# ─────────────────────────────────────────────────────────────────
# EXPERIMENT 3: exp_ablation_simpo (from Step 3)
# ─────────────────────────────────────────────────────────────────
EXP="exp_ablation_simpo"
CFG="experiments/$EXP/config.sh"
EXP_DIR="outputs/$EXP"

echo "============================================================"
echo "[3/3] $EXP — starting from Step 3 (pair building)"
echo "Time: $(date)"
echo "============================================================"

source "$CFG"
export EXP_NAME="$EXP"
setup_baseline_links "$EXP_DIR"

echo "2" > "$EXP_DIR/.checkpoint"
echo "  Set checkpoint to 2 (skipping baseline generation)"

export RESUME=1
bash "$SCRIPT_DIR/demo8_dpo_driver.sh" 2>&1 | tee "$EXP_DIR/ablation_run.log"

echo ""
echo "$EXP completed at $(date)"
echo ""

# ─────────────────────────────────────────────────────────────────
# Combined comparison report
# ─────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "All ablation experiments completed!"
echo "Generating combined comparison..."
echo "============================================================"

REPORT_DIR="reports/ablation_comparison"
mkdir -p "$REPORT_DIR"

python3 -c "
import csv, json, os
from pathlib import Path

experiments = ['exp_final_50k', 'exp_ablation_dpo', 'exp_ablation_cdpo', 'exp_ablation_simpo']
labels = ['Baseline (original DPO)', 'DPO (improved)', 'cDPO', 'SimPO']

rows = []
for exp, label in zip(experiments, labels):
    csv_path = Path(f'reports/{exp}/summary.csv')
    if csv_path.exists():
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                row['experiment'] = exp
                row['label'] = label
                rows.append(row)
    else:
        print(f'WARNING: {csv_path} not found')

# Write combined CSV
out_csv = Path('$REPORT_DIR/ablation_results.csv')
if rows:
    with open(out_csv, 'w', newline='') as f:
        fields = ['experiment', 'label'] + [k for k in rows[0] if k not in ('experiment', 'label')]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f'Combined results: {out_csv}')

# Write markdown summary
md = Path('$REPORT_DIR/ablation_summary.md')
with open(md, 'w') as f:
    f.write('# DPO Ablation Study: LiFePO4\n\n')
    f.write('## Experiment Variants\n\n')
    f.write('| Variant | Loss | Beta | LR | Steps | Label Smoothing | SimPO Gamma |\n')
    f.write('|---------|------|------|----|-------|----------------|-------------|\n')
    for exp in experiments:
        hp_path = Path(f'outputs/{exp}/dpo/checkpoint/hparams.json')
        if hp_path.exists():
            hp = json.loads(hp_path.read_text())
            lt = hp.get('loss_type', 'dpo')
            beta = hp.get('beta', '?')
            lr = hp.get('lr', '?')
            steps = hp.get('steps', '?')
            ls = hp.get('label_smoothing', '-')
            sg = hp.get('simpo_gamma', '-')
            f.write(f'| {exp} | {lt} | {beta} | {lr} | {steps} | {ls} | {sg} |\n')

    f.write('\n## Results Comparison\n\n')
    f.write('| Model | Validity | Stability (Ehull<0.05) | Hit Rate | Energy Mean | Energy Median |\n')
    f.write('|-------|----------|----------------------|----------|-------------|---------------|\n')
    for r in rows:
        model = r.get('model', '?')
        exp = r.get('experiment', '?')
        vr = r.get('valid_rate', '?')
        sr = r.get('stability_rate', '?')
        hr = r.get('hit_rate', '?')
        em = r.get('score_mean', '?')
        emd = r.get('score_median', '?')
        f.write(f'| {exp}/{model} | {vr} | {sr} | {hr} | {em} | {emd} |\n')

    f.write('\n## Conclusion\n\n')
    f.write('See individual experiment reports in reports/exp_ablation_*/summary.md\n')

print(f'Summary report: {md}')
"

TOTAL_END=$(date +%s)
TOTAL_ELAPSED=$(( (TOTAL_END - TOTAL_START) / 3600 ))
echo ""
echo "============================================================"
echo "Ablation suite finished at $(date)"
echo "Total elapsed: ~${TOTAL_ELAPSED} hours"
echo "Reports: $REPORT_DIR/"
echo "============================================================"
