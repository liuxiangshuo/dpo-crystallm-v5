# exp_sft_rl_v4 给 GPT 的背景说明

你是我的代码助手，请基于以下项目背景帮助我修改 `exp_sft_rl_v4` pipeline。请先理解流程，再给出“最小改动、可复现”的修改方案与命令。

## 项目与实验目标

- 项目：`dpo-crystallm`
- 实验：`exp_sft_rl_v4`
- 任务：多组分晶体生成与优化，采用 **SFT + DPO** 两阶段训练
- 目标组分：`LiFePO4, NaCl, TiO2`
- 当前是 pilot 规模：每目标 `NUM_SAMPLES=2000`

## 入口与主控

- 实验入口：`experiments/exp_sft_rl_v4/run.sh`
  - `source experiments/exp_sft_rl_v4/config.sh`
  - `exec bash scripts/run_sft_rl_pipeline.sh`
- 主控脚本：`scripts/run_sft_rl_pipeline.sh`
  - 包含 Phase 1~6、checkpoint/resume、质量门限、日志输出

## Pipeline 分阶段

### Phase 1 Baseline 生成+打分

对每个 target：

1. `scripts/40_generate_cifs_crystallm.py`
2. `scripts/11_validate_cifs.py`
3. `scripts/12_label_cifs.py`
4. `scripts/35_score_dir_matgl.py`
5. `scripts/36_estimate_ehull.py`
6. `scripts/48_compute_composite_reward.py`
7. 检查 valid/scored 门限

### Phase 2 SFT 数据与训练

- 数据准备：`scripts/47_prepare_sft_data.py`
- 训练：`scripts/33_train_sft_crystallm.py`
- v4 当前仅开 `SFT_BRANCHES="lora64"`

### Phase 3 SFT 重采样 + 重新打分 + 配对

- 同样执行生成/校验/打分/ehull/reward
- 配对脚本：`scripts/41_build_pairs_with_token_filter.py`

### Phase 4 多目标合并 Pair + DPO

- 合并：`scripts/49_merge_multi_target_data.py --mode pairs`
- 训练：`scripts/32_train_dpo_crystallm.py`

### Phase 5 最终评估

- DPO 模型再生成并打分
- 三方评估：`scripts/50_evaluate_three_way.py`（Baseline vs SFT vs DPO）

### Phase 6 可视化

- `scripts/51_visualize_structures.py`

## 当前关键配置（v4）

文件：`experiments/exp_sft_rl_v4/config.sh`

- targets: `LiFePO4,NaCl,TiO2`
- samples: `2000`
- SFT: `lora64`（rank=64）
- DPO: `steps=2000, beta=2.5, lr=1e-7, loss=dpo`
- Reward weighted DPO: 开启（`DPO_REWARD_WEIGHTED=1`, `DPO_REWARD_ALPHA=1.0`）
- 当前复合奖励权重：`energy/structure/difficulty/composition = 0.4/0.2/0.2/0.2`

## difficulty 计算方式（当前实现）

文件：`scripts/48_compute_composite_reward.py`

- 函数：`compute_r_difficulty`
- 逻辑：空间群 -> 晶系 -> 基础分
  - triclinic 0.10, monoclinic 0.30, orthorhombic 0.50, tetragonal 0.65, trigonal 0.60, hexagonal 0.80, cubic 0.95
- SG#1 (P1) 额外 -0.05（下限 0）
- 若提供 `sg_stability`，则与基础分 50/50 融合
- 最终进入 `r_total = w_e*r_energy + w_s*r_structure + w_d*r_difficulty + w_c*r_composition`

## 输出结构（主要）

- `outputs/exp_sft_rl_v4/<target>/baseline/...`
- `outputs/exp_sft_rl_v4/sft_lora64/checkpoint/...`
- `outputs/exp_sft_rl_v4/<target>/sft_lora64/pairs/pairs.jsonl`
- `outputs/exp_sft_rl_v4/dpo_lora64/checkpoint/...`
- `reports/exp_sft_rl_v4/...`

## 你需要做的事

1. 先复述你理解的 pipeline 与依赖关系，避免误改。
2. 给出具体改动方案（改哪些文件、哪些变量/函数、为何这样改）。
3. 给出最小验证步骤（看哪些日志/文件判断生效）。
4. 如果涉及重跑，请明确“至少从哪个 Phase 重跑”。

## 关键代码（可直接参考）

### 1) 实验入口：加载 v4 配置并启动总管线

文件：`experiments/exp_sft_rl_v4/run.sh`

```bash
source "$SCRIPT_DIR/config.sh"
exec bash "$PROJECT_ROOT/scripts/run_sft_rl_pipeline.sh"
```

### 2) 总管线读取奖励权重并传给复合奖励脚本

文件：`scripts/run_sft_rl_pipeline.sh`

```bash
REWARD_W_ENERGY=${REWARD_W_ENERGY:-0.4}
REWARD_W_STRUCTURE=${REWARD_W_STRUCTURE:-0.2}
REWARD_W_DIFFICULTY=${REWARD_W_DIFFICULTY:-0.2}
REWARD_W_COMPOSITION=${REWARD_W_COMPOSITION:-0.2}
```

```bash
python "$SCRIPT_DIR/48_compute_composite_reward.py" \
  --w_energy "$REWARD_W_ENERGY" \
  --w_structure "$REWARD_W_STRUCTURE" \
  --w_difficulty "$REWARD_W_DIFFICULTY" \
  --w_composition "$REWARD_W_COMPOSITION"
```

### 3) difficulty 的核心实现（空间群 -> 晶系 -> 分数）

文件：`scripts/48_compute_composite_reward.py`

```python
_CRYSTAL_SYSTEM_DIFFICULTY = {
    "triclinic":     0.10,
    "monoclinic":    0.30,
    "orthorhombic":  0.50,
    "tetragonal":    0.65,
    "trigonal":      0.60,
    "hexagonal":     0.80,
    "cubic":         0.95,
}
```

```python
def compute_r_difficulty(cif_dir: Path, filenames: list, sg_stability: dict, **_kwargs) -> list:
    ...
    sg_number = sga.get_space_group_number()
    cs = _sg_crystal_system(sg_number)
    base_diff = _CRYSTAL_SYSTEM_DIFFICULTY.get(cs, 0.50)
    if sg_number == 1:
        base_diff = max(0.0, base_diff - 0.05)
    emp_rate = sg_stability.get(sg_sym_ascii, sg_stability.get(sg_sym_raw, None))
    if emp_rate is not None:
        base_diff = 0.5 * base_diff + 0.5 * emp_rate
    ...
```

### 4) 复合奖励总公式

文件：`scripts/48_compute_composite_reward.py`

```python
total = (w_e * r_energy[i] +
         w_s * r_structure[i] +
         w_d * r_difficulty[i] +
         w_c * r_composition[i])
```

### 5) Pair 构建：有 reward_csv 时按 r_total 排序

文件：`scripts/41_build_pairs_with_token_filter.py`

```python
if reward_scores:
    rank_scores = {}
    for fn in scores:
        rank_scores[fn] = reward_scores.get(fn, 0.0)
else:
    rank_scores = {fn: -v for fn, v in scores.items()}
```

```python
candidates_sorted_by_prompt[p] = sorted(
    cands, key=lambda fn: rank_scores.get(fn, 0.0), reverse=True)
```

### 6) DPO reward-weighted 关键逻辑

文件：`scripts/32_train_dpo_crystallm.py`

```python
reward_margin = 0.0
if args.reward_weighted:
    r_c = float(ex.get("chosen_reward", 0.0) or 0.0)
    r_r = float(ex.get("rejected_reward", 0.0) or 0.0)
    reward_margin = args.reward_alpha * (r_c - r_r)
```

```python
loss = -F.logsigmoid(args.beta * adv + reward_margin) / args.grad_accum_steps
```

### 7) 多目标 pairs 合并时 target 推断

文件：`scripts/49_merge_multi_target_data.py`

```python
def _infer_target(exp_path: Path) -> str:
    name = exp_path.name
    if name in _PHASE_NAMES:
        return exp_path.parent.name
    for pfx in _PHASE_PREFIXES:
        if name.startswith(pfx):
            return exp_path.parent.name
    return name
```
