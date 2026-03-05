# exp_sft_rl_v4 Pipeline 梳理与修改指南

## 1. 目标与定位

`exp_sft_rl_v4` 是一个多目标组分（`LiFePO4`/`NaCl`/`TiO2`）的两阶段训练流水线：

1. 先做 SFT（稳定样本监督微调）
2. 再做 DPO（基于偏好对的强化偏好优化）

并在每个关键阶段做：

- CIF 生成
- 有效性校验
- MatGL 能量评分
- Ehull 估计
- 复合奖励计算
- 三方评估（Baseline vs SFT vs DPO）

---

## 2. 入口与调用关系（从哪里开始跑）

### 2.1 实验入口

- `experiments/exp_sft_rl_v4/run.sh`
  - `source experiments/exp_sft_rl_v4/config.sh`
  - `exec bash scripts/run_sft_rl_pipeline.sh`

### 2.2 总控脚本

- `scripts/run_sft_rl_pipeline.sh`
  - 按 Phase 1~6 顺序调度所有子脚本
  - 负责检查点、质量门限、分支循环、多目标合并

---

## 3. 配置总览（主要改这里）

主配置文件：`experiments/exp_sft_rl_v4/config.sh`

### 3.1 实验标识与目标

- `EXP_NAME=exp_sft_rl_v4`
- `TARGETS="LiFePO4,NaCl,TiO2"`
- `PROMPT_Z_MAP="LiFePO4:4,NaCl:4,TiO2:4"`

### 3.2 采样与生成

- `NUM_SAMPLES`：每个目标生成样本数（当前 2000）
- `TOP_K` / `TEMPERATURE`
- `TEMPERATURE_RANGE` / `TOP_K_RANGE`：每样本随机多样性区间
- `MAX_TOKENS` / `GEN_BATCH_SIZE` / `MAX_RETRIES`

### 3.3 质量门限

- `MIN_VALID_CIFS`
- `MIN_SCORED_CIFS`
- `MIN_PAIRS`

### 3.4 Pair 构建

- `PAIR_STRATEGY`（`trimmed` / `all`）
- `PAIR_GAP`
- `PAIR_MIN_PER_PROMPT`
- `PAIR_MAX_PER_PROMPT`

### 3.5 复合奖励权重（你常改的地方）

- `REWARD_W_ENERGY`
- `REWARD_W_STRUCTURE`
- `REWARD_W_DIFFICULTY`
- `REWARD_W_COMPOSITION`

### 3.6 SFT（Stage 1）

当前 v4 只启用：

- `SFT_BRANCHES="lora64"`

分支参数：

- `SFT_lora64_STRATEGY=lora`
- `SFT_lora64_LR`
- `SFT_lora64_STEPS`
- `SFT_lora64_GRAD_ACCUM`
- `SFT_lora64_WARMUP`
- `SFT_lora64_LORA_RANK`
- `SFT_lora64_LORA_TARGETS`
- `SFT_lora64_WEIGHT_DECAY`

### 3.7 DPO（Stage 2）

- `DPO_STEPS` / `DPO_LR` / `DPO_BETA`
- `DPO_LOSS_TYPE`（`dpo/cdpo/simpo`）
- `DPO_REWARD_WEIGHTED`（0/1）
- `DPO_REWARD_ALPHA`
- `DPO_GRAD_ACCUM` / `DPO_WARMUP` / `DPO_WEIGHT_DECAY`

### 3.8 路径与环境

- `CRYSTALLM_CKPT_DIR`
- `CRYSTALLM_PKG_DIR`
- `TRAINING_DATA_DIR`
- `MATGL_FIX_LD_LIBRARY_PATH`

---

## 4. Pipeline 逐阶段拆解（Phase 1~6）

## Phase 1：Baseline 生成与打分

每个 `target` 执行一次：

1. 生成 CIF  
   `scripts/40_generate_cifs_crystallm.py`

2. 校验 CIF  
   `scripts/11_validate_cifs.py`

3. 目标标签  
   `scripts/12_label_cifs.py`

4. MatGL 能量评分  
   `scripts/35_score_dir_matgl.py`

5. `labels.csv + ehull_scores.csv` 合并为 `eval.csv`（内嵌 python）

6. Ehull 估计  
   `scripts/36_estimate_ehull.py`

7. 复合奖励  
   `scripts/48_compute_composite_reward.py`

8. 奖励离散度检查  
   `check_reward_spread()`（总控脚本内函数）

质量门限：

- `valid_cifs` 数量 < `MIN_VALID_CIFS` 直接终止
- `ehull_scores.csv` 数量 < `MIN_SCORED_CIFS` 直接终止

输出目录（按目标）：

- `outputs/exp_sft_rl_v4/<target>/baseline/raw_cifs`
- `outputs/exp_sft_rl_v4/<target>/baseline/scored`

---

## Phase 2：SFT 数据准备与训练

1. 聚合多目标稳定样本为一个 SFT 数据集  
   `scripts/47_prepare_sft_data.py`

- 输入：各目标的 `ehull_estimates.csv` + `raw_cifs`
- 输出：`outputs/exp_sft_rl_v4/sft_shared/sft_data.jsonl`

2. 按分支训练 SFT（v4 当前只有 `lora64`）  
   `scripts/33_train_sft_crystallm.py`

- 输出 ckpt：`outputs/exp_sft_rl_v4/sft_lora64/checkpoint/ckpt.pt`
- 同时会保存 `best_ckpt.pt`、`training_log.jsonl`、`hparams.json`

---

## Phase 3：SFT 模型重采样 + 打分 + 配对

每个 `branch × target`：

1. 用 SFT ckpt 重新生成  
2. 校验/标签/MatGL/Ehull/复合奖励（同 Phase 1）  
3. 构建偏好对  
   `scripts/41_build_pairs_with_token_filter.py`

Pair 构建要点：

- 支持 `reward_csv` 时按 `r_total` 排序
- 过滤超过 `MAX_TOKENS` 的 chosen/rejected
- `PAIR_GAP` 控制正负样本差距
- `trimmed` 时用 top-q 与 bottom-q

输出目录：

- `outputs/exp_sft_rl_v4/<target>/sft_lora64/scored`
- `outputs/exp_sft_rl_v4/<target>/sft_lora64/pairs/pairs.jsonl`

---

## Phase 4：多目标合并 Pair + DPO 训练

1. 汇总可用目标的 pair（跳过空目标）  
   `scripts/49_merge_multi_target_data.py --mode pairs`

2. 质量门限：`merged_pairs` < `MIN_PAIRS` 则跳过该分支

3. 在 SFT ckpt 基础上训练 DPO  
   `scripts/32_train_dpo_crystallm.py`

输出目录：

- `outputs/exp_sft_rl_v4/dpo_lora64/checkpoint/ckpt.pt`
- `best_ckpt.pt`、`training_log.jsonl`、`hparams.json`

---

## Phase 5：最终评估与对比报告

每个 `branch × active_target`：

1. 用 DPO ckpt 生成
2. 校验/标签/评分/Ehull/复合奖励
3. 三方评估报告  
   `scripts/50_evaluate_three_way.py`

分支级汇总：

- `reports/exp_sft_rl_v4/three_way_lora64/...`
- `reports/exp_sft_rl_v4/sft_rl_summary.md`

---

## Phase 6：结构可视化

- `scripts/51_visualize_structures.py`
- 自动选择 backend：
  - 有 VESTA 可执行文件时用 `vesta`
  - 否则用 `ase`

输出目录：

- `reports/exp_sft_rl_v4/visualizations`

---

## 5. 检查点与断点续跑机制

总控脚本通过：

- `outputs/exp_sft_rl_v4/.checkpoint`

记录已完成的 Phase 编号，配合：

- `RESUME=1 bash experiments/exp_sft_rl_v4/run.sh`

可跳过已完成阶段继续跑。

注意：

- 改了上游关键配置（如奖励权重、pair策略、采样参数）后，不建议直接从后续 Phase 续跑；应从受影响阶段重新开始。

---

## 6. 关键输入输出文件速查（改动时最常看）

### 6.1 每目标 baseline

- `.../baseline/raw_cifs/*.cif`
- `.../baseline/scored/labels.csv`
- `.../baseline/scored/ehull_scores.csv`
- `.../baseline/scored/eval.csv`
- `.../baseline/scored/ehull_estimates.csv`
- `.../baseline/scored/composite_reward.csv`
- `.../baseline/scored/composite_reward_summary.json`

### 6.2 SFT

- `.../sft_shared/sft_data.jsonl`
- `.../sft_lora64/checkpoint/{ckpt.pt,best_ckpt.pt}`

### 6.3 Pair 与 DPO

- `.../<target>/sft_lora64/pairs/pairs.jsonl`
- `.../dpo_lora64/merged_pairs.jsonl`
- `.../dpo_lora64/checkpoint/{ckpt.pt,best_ckpt.pt}`

### 6.4 报告

- `reports/exp_sft_rl_v4/sft_rl_summary.md`
- `reports/exp_sft_rl_v4/three_way_lora64/...`
- `reports/exp_sft_rl_v4/visualizations/...`

---

## 7. 你后续修改时的建议入口

## 场景 A：改奖励权重

改：`experiments/exp_sft_rl_v4/config.sh`

- `REWARD_W_ENERGY`
- `REWARD_W_STRUCTURE`
- `REWARD_W_DIFFICULTY`
- `REWARD_W_COMPOSITION`

影响阶段：Phase 1 / 3 / 5（复合奖励计算）和 Phase 3/4（pair 排序与 DPO 数据）

---

## 场景 B：改 DPO 偏好学习形态

改：`config.sh` 中：

- `DPO_LOSS_TYPE`
- `DPO_BETA`
- `DPO_REWARD_WEIGHTED`
- `DPO_REWARD_ALPHA`

如需改公式细节：`scripts/32_train_dpo_crystallm.py`

---

## 场景 C：改 Pair 构建策略

改：`config.sh` 中：

- `PAIR_STRATEGY`
- `PAIR_GAP`
- `PAIR_MIN_PER_PROMPT`
- `PAIR_MAX_PER_PROMPT`

如需改算法细节：`scripts/41_build_pairs_with_token_filter.py`

---

## 场景 D：加/减目标组分

改：`TARGETS` 与 `PROMPT_Z_MAP`

注意同步检查：

- 质量门限是否仍合理
- 各目标样本平衡是否满足 `49_merge_multi_target_data.py --balance uniform`

---

## 8. 最小运行命令

```bash
bash experiments/exp_sft_rl_v4/run.sh
```

断点续跑：

```bash
RESUME=1 bash experiments/exp_sft_rl_v4/run.sh
```

---

## 9. 当前 v4 默认关键值（便于对照）

- 目标：`LiFePO4,NaCl,TiO2`
- 每目标采样：`2000`
- SFT 分支：`lora64`
- DPO：`steps=2000, lr=1e-7, beta=2.5, loss=dpo`
- 奖励权重：`0.4/0.2/0.2/0.2`（energy/structure/difficulty/composition）

> 如果你后续要做“权重扫描实验”，建议把该节维护成变更日志，避免重复跑错配置。

