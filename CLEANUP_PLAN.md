# DPO-CrystaLLM 项目清理和优化计划

## 目标
- 删除冗余代码和旧实验
- 只保留 exp_sft_rl_v5 pipeline
- 优化 pipeline 结构（模块化拆分）

---

## 一、删除废弃脚本

### 1.1 已废弃的Python脚本（建议删除）

| 脚本 | 替代方案 | 说明 |
|------|----------|------|
| `10_generate_cifs_stub.py` | `40_generate_cifs_crystallm.py` | 早期测试stub |
| `13_build_dpo_pairs.py` | `41_build_pairs_with_token_filter.py` | 旧配对构建 |
| `14_train_dpo_smoke.py` | 集成到 pipeline | 早期DPO测试 |
| `15_make_local_tokenizer.py` | 不再需要 | 本地tokenizer（2个文件） |
| `16_train_dpo_local_model.py` | `32_train_dpo_crystallm.py` | 旧训练脚本 |
| `20_score_matgl_proxy.py` | `35_score_dir_matgl.py` | 旧评分脚本 |
| `21_build_pairs_phase3.py` | `41_build_pairs_with_token_filter.py` | 旧配对构建 |
| `25_build_pairs_phase3_lifepo4.py` | `41_build_pairs_with_token_filter.py` | 专用脚本 |
| `26_build_pairs_phase3_lifepo4_many.py` | `41_build_pairs_with_token_filter.py` | 专用脚本 |
| `34_compare_delta_baseline_vs_dpo.py` | `50_evaluate_three_way.py` | 旧对比脚本 |
| `42_generate_comparison_report.py` | `50_evaluate_three_way.py` | 旧报告生成 |
| `49_merge_multi_target_data.py` | `shared/pair_merge.py` | 被模块替代 |

**预计删除: 13个Python脚本**

### 1.2 保留的Python脚本（v5 pipeline核心）

```
Phase 1: 生成和评分
├── 40_generate_cifs_crystallm.py    # 生成CIF
├── 11_validate_cifs.py              # 验证CIF
├── 12_label_cifs.py                 # 标记CIF
├── 35_score_dir_matgl.py            # MatGL评分
├── 36_estimate_ehull.py             # Ehull估计
└── 48_compute_composite_reward.py   # 复合奖励

Phase 2: SFT训练
├── 47_prepare_sft_data.py           # 准备SFT数据
└── 33_train_sft_crystallm.py         # SFT训练

Phase 3: 配对构建
└── 41_build_pairs_with_token_filter.py  # 构建配对

Phase 4: DPO训练
└── 32_train_dpo_crystallm.py         # DPO训练

Phase 5: 评估
└── 50_evaluate_three_way.py          # 三方评估

Phase 6: 可视化
└── 51_visualize_structures.py        # CIF导出

共享模块
└── shared/
    ├── __init__.py
    ├── pipeline_utils.py             # Pipeline工具
    ├── pair_merge.py                 # 配对合并
    └── lora_utils.py                 # LoRA工具

工具脚本（可选保留）
├── 00_check_env.py                   # 环境检查
├── 01_smoke_test_cuda.py             # CUDA测试
├── 31_logprob_check.py               # 日志概率检查
├── 37_compute_novelty.py             # 新颖性计算
├── 38_analyze_structures.py          # 结构分析
├── 43_analyze_pair_quality.py        # 配对质量分析
└── test_shared_modules.py            # 模块测试
```

### 1.3 废弃的Shell脚本（建议删除）

| 脚本 | 说明 |
|------|------|
| `demo8_dpo_driver.sh` | 旧驱动脚本 |
| `resume_ablation_tmux.sh` | 特定用途 |
| `run_ablation_suite.sh` | 消融实验（可保留） |
| `run_beta_sweep.sh` | 参数扫描 |
| `run_factor_ablation.sh` | 因子消融 |
| `run_multi_target.sh` | 多目标（被pipeline替代） |
| `run_sft_experiment.sh` | 旧SFT脚本 |

**建议保留:**
- `run_sft_rl_pipeline.sh` (主pipeline)
- `run_exp_sft_rl_v5_tmux.sh` (tmux运行)
- `check_exp_status.sh` (状态检查)

---

## 二、删除旧实验目录

### 2.1 建议删除的实验（已完成/废弃）

```
experiments/
├── exp_20260203_180121_LiFePO4/      # 早期实验
├── exp_20260204_132341_LiFePO4_test/   # 测试实验
├── exp_20260204_165505_LiFePO4_fixed/# 修复实验
├── exp_LiFePO4_prod_ready/             # 已完成
├── exp_sft_rl/                         # v1版本
├── exp_sft_rl_v2/                      # v2版本
├── exp_sft_rl_v3/                      # v3版本
├── exp_sft_rl_v4/                      # v4版本（可保留config参考）
├── exp_sft_rl_smoke/                   # smoke测试
├── exp_sft_stable/                     # 已完成
├── exp_ablation_dpo/                   # 消融（可选保留）
├── exp_ablation_cdpo/                  # 消融（可选保留）
├── exp_ablation_simpo/                 # 消融（可选保留）
├── exp_multi_LiFePO4/                  # 多目标（已完成）
├── exp_multi_NaCl/                     # 多目标（已完成）
├── exp_multi_TiO2/                     # 多目标（已完成）
├── exp_multi_BaTiO3/                   # 多目标（已完成）
├── exp_multi_Li3PS4/                   # 多目标（已完成）
├── exp_final_50k/                      # 大规模（已完成）
└── exp_smoke_test/                     # 测试
```

**保留:**
- `exp_sft_rl_v5/` - 当前主实验
- `exp_sft_rl_v4/` - 参考配置（可选）
- `_template/` - 模板

---

## 三、Pipeline 结构优化

### 3.1 当前问题

`run_sft_rl_pipeline.sh` (1671行) 过于庞大，包含：
- 6个Phase的逻辑
- 大量辅助函数
- 复杂的错误处理
- 混合的配置和逻辑

### 3.2 优化方案：模块化拆分

```
scripts/
├── pipeline/
│   ├── main.sh                       # 主入口 (~100行)
│   ├── config.sh                     # 配置加载 (~50行)
│   ├── lib/
│   │   ├── logging.sh                # 日志函数
│   │   ├── timing.sh                 # 计时函数
│   │   ├── checkpoint.sh             # 检查点管理
│   │   └── error.sh                  # 错误处理
│   └── phases/
│       ├── phase1_baseline.sh        # Phase 1: 基线生成
│       ├── phase2_sft_train.sh       # Phase 2: SFT训练
│       ├── phase3_resample.sh       # Phase 3: 重采样
│       ├── phase4_dpo_train.sh       # Phase 4: DPO训练
│       ├── phase5_evaluate.sh        # Phase 5: 评估
│       └── phase6_visualize.sh       # Phase 6: 可视化
```

### 3.3 优化后的目录结构

```
dpo-crystallm/                      # 根目录 (~10个文件)
├── README.md
├── requirements.txt                # 合并3个requirements
├── .gitignore
├── experiments/
│   ├── _template/                  # 实验模板
│   └── exp_sft_rl_v5/              # 当前实验
│       ├── config.sh
│       └── run.sh
├── scripts/
│   ├── pipeline/                   # 新pipeline目录
│   │   ├── main.sh
│   │   ├── lib/
│   │   └── phases/
│   ├── shared/                     # 共享模块
│   ├── train/                      # 训练脚本
│   ├── generate/                   # 生成脚本
│   ├── score/                      # 评分脚本
│   ├── analyze/                    # 分析脚本
│   └── tools/                      # 工具脚本
├── reports/
│   └── exp_sft_rl_v5/
├── outputs/                        # gitignored
└── logs/                          # gitignored
```

---

## 四、实施步骤

### 阶段1: 清理废弃文件
1. 删除废弃Python脚本 (13个)
2. 删除废弃Shell脚本 (5个)
3. 删除旧实验目录 (保留v5)
4. 提交commit

### 阶段2: Pipeline模块化
1. 创建新的pipeline目录结构
2. 拆分run_sft_rl_pipeline.sh
3. 测试新pipeline
4. 提交commit

### 阶段3: 优化和测试
1. 合并requirements文件
2. 更新README
3. 全面测试pipeline
4. 提交最终commit

---

## 五、预期效果

### 文件数量
- 当前: ~60个脚本文件
- 清理后: ~25个核心脚本
- 减少: ~60%

### 代码行数
- 当前: ~1671行 (pipeline)
- 优化后: ~200行/模块 × 6 = ~1200行 (更清晰)

### 维护性
- 模块化结构，易于理解
- 独立测试每个phase
- 清晰的依赖关系

---

## 六、风险控制

### 备份策略
```bash
# 清理前创建备份分支
git checkout -b backup/pre-cleanup-$(date +%Y%m%d)
git push origin backup/pre-cleanup-$(date +%Y%m%d)

# 清理过程中分阶段commit
# 每个阶段完成后测试
```

### 回滚方案
- 所有删除操作通过git管理
- 可随时从备份分支恢复
- 保留v5实验完整配置

---

是否需要我开始实施这个清理计划？
建议先确认：
1. 哪些旧实验需要保留（如消融实验）
2. 哪些工具脚本需要保留
3. 清理后是否立即运行测试
