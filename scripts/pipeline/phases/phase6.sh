# =====================================================================
# PHASE 6: Structure Visualisation
# =====================================================================
record_timing "6" "start"
echo ""
echo "=========================================="
echo "Phase 6: Structure Visualisation"
echo "=========================================="

BRANCH_STR=$(IFS=','; echo "${BRANCH_LIST[*]}")
TARGET_STR=$(IFS=','; echo "${TARGET_LIST[*]}")

VIZ_BACKEND="ase"
VESTA_BIN="${HOME}/tools/VESTA/VESTA"
if [ -x "$VESTA_BIN" ]; then
    VIZ_BACKEND="vesta"
fi

conda run -n myenv python "$SCRIPT_DIR/51_visualize_structures.py" \
    --exp_dir "$EXP_DIR" \
    --targets "$TARGET_STR" \
    --branches "$BRANCH_STR" \
    --top_n 10 \
    --out_dir "$REPORT_DIR/visualizations" \
    --export_cifs \
    || echo "WARNING: CIF export failed (non-fatal)"

warn_if_no_visualizations "$REPORT_DIR/visualizations"

mark_step_done 6

