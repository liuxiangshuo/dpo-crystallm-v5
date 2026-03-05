# exp_sft_rl_v5 实验文件索引

> 生成时间: 2026-03-04  
> 实验状态: ✅ 完成 (Phase 1-6)

---

## 快速导航

### 核心报告
- [实验总体摘要](reports/exp_sft_rl_v5/sft_rl_summary.md)
- [LoRA64 汇总数据](reports/exp_sft_rl_v5/three_way_lora64/three_way_summary.csv)
- [Full FT 汇总数据](reports/exp_sft_rl_v5/three_way_full_ft/three_way_summary.csv)

### 详细对比报告
| 目标 | LoRA64 | Full FT |
|------|--------|---------|
| LiFePO4 | [查看报告](reports/exp_sft_rl_v5/three_way_lora64/LiFePO4/three_way_comparison.md) | [查看报告](reports/exp_sft_rl_v5/three_way_full_ft/LiFePO4/three_way_comparison.md) |
| NaCl | [查看报告](reports/exp_sft_rl_v5/three_way_lora64/NaCl/three_way_comparison.md) | [查看报告](reports/exp_sft_rl_v5/three_way_full_ft/NaCl/three_way_comparison.md) |
| TiO2 | [查看报告](reports/exp_sft_rl_v5/three_way_lora64/TiO2/three_way_comparison.md) | [查看报告](reports/exp_sft_rl_v5/three_way_full_ft/TiO2/three_way_comparison.md) |

---

## 实验配置

- [实验配置文件](experiments/exp_sft_rl_v5/config.sh)

### 关键参数
```
实验名称: exp_sft_rl_v5
目标材料: LiFePO4, NaCl, TiO2
样本数: 2000 per target
SFT分支: lora64, full_ft
SFT步数: 6000
DPO步数: 12000
DPO beta: 2.5
Reward权重: proxy=0.70, geom=0.10, comp=0.10, novel=0.10
```

---

## 模型检查点

### SFT模型
| 分支 | 最佳模型 | 最终模型 | 超参数 |
|------|----------|----------|--------|
| LoRA64 | [best_ckpt.pt](outputs/exp_sft_rl_v5/sft_lora64/checkpoint/best_ckpt.pt) (99.5MB) | [ckpt.pt](outputs/exp_sft_rl_v5/sft_lora64/checkpoint/ckpt.pt) | [hparams.json](outputs/exp_sft_rl_v5/sft_lora64/checkpoint/hparams.json) |
| Full FT | [best_ckpt.pt](outputs/exp_sft_rl_v5/sft_full_ft/checkpoint/best_ckpt.pt) (98.8MB) | [ckpt.pt](outputs/exp_sft_rl_v5/sft_full_ft/checkpoint/ckpt.pt) | [hparams.json](outputs/exp_sft_rl_v5/sft_full_ft/checkpoint/hparams.json) |

### DPO模型
| 分支 | 最佳模型 | 最终模型 | 超参数 |
|------|----------|----------|--------|
| LoRA64 | [best_ckpt.pt](outputs/exp_sft_rl_v5/dpo_lora64/checkpoint/best_ckpt.pt) (98.8MB) | [ckpt.pt](outputs/exp_sft_rl_v5/dpo_lora64/checkpoint/ckpt.pt) | [hparams.json](outputs/exp_sft_rl_v5/dpo_lora64/checkpoint/hparams.json) |
| Full FT | [best_ckpt.pt](outputs/exp_sft_rl_v5/dpo_full_ft/checkpoint/best_ckpt.pt) (98.8MB) | [ckpt.pt](outputs/exp_sft_rl_v5/dpo_full_ft/checkpoint/ckpt.pt) | [hparams.json](outputs/exp_sft_rl_v5/dpo_full_ft/checkpoint/hparams.json) |

---

## 数据文件

### 训练数据
- [SFT训练数据](outputs/exp_sft_rl_v5/sft_shared/sft_data.jsonl) (453样本)
- [LoRA64 DPO配对](outputs/exp_sft_rl_v5/dpo_lora64/merged_pairs.jsonl) (450对)
- [Full FT DPO配对](outputs/exp_sft_rl_v5/dpo_full_ft/merged_pairs.jsonl) (450对)

### 评估数据 (LiFePO4)
| 阶段 | 评估CSV | 能量分数 | 复合奖励 |
|------|---------|----------|----------|
| Baseline | [eval.csv](outputs/exp_sft_rl_v5/LiFePO4/baseline/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/LiFePO4/baseline/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/LiFePO4/baseline/scored/composite_reward.csv) |
| SFT LoRA64 | [eval.csv](outputs/exp_sft_rl_v5/LiFePO4/sft_lora64/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/LiFePO4/sft_lora64/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/LiFePO4/sft_lora64/scored/composite_reward.csv) |
| SFT Full FT | [eval.csv](outputs/exp_sft_rl_v5/LiFePO4/sft_full_ft/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/LiFePO4/sft_full_ft/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/LiFePO4/sft_full_ft/scored/composite_reward.csv) |
| DPO LoRA64 | [eval.csv](outputs/exp_sft_rl_v5/LiFePO4/dpo_lora64/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/LiFePO4/dpo_lora64/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/LiFePO4/dpo_lora64/scored/composite_reward.csv) |
| DPO Full FT | [eval.csv](outputs/exp_sft_rl_v5/LiFePO4/dpo_full_ft/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/LiFePO4/dpo_full_ft/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/LiFePO4/dpo_full_ft/scored/composite_reward.csv) |

### 评估数据 (NaCl)
| 阶段 | 评估CSV | 能量分数 | 复合奖励 |
|------|---------|----------|----------|
| Baseline | [eval.csv](outputs/exp_sft_rl_v5/NaCl/baseline/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/NaCl/baseline/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/NaCl/baseline/scored/composite_reward.csv) |
| SFT LoRA64 | [eval.csv](outputs/exp_sft_rl_v5/NaCl/sft_lora64/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/NaCl/sft_lora64/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/NaCl/sft_lora64/scored/composite_reward.csv) |
| SFT Full FT | [eval.csv](outputs/exp_sft_rl_v5/NaCl/sft_full_ft/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/NaCl/sft_full_ft/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/NaCl/sft_full_ft/scored/composite_reward.csv) |
| DPO LoRA64 | [eval.csv](outputs/exp_sft_rl_v5/NaCl/dpo_lora64/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/NaCl/dpo_lora64/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/NaCl/dpo_lora64/scored/composite_reward.csv) |
| DPO Full FT | [eval.csv](outputs/exp_sft_rl_v5/NaCl/dpo_full_ft/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/NaCl/dpo_full_ft/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/NaCl/dpo_full_ft/scored/composite_reward.csv) |

### 评估数据 (TiO2)
| 阶段 | 评估CSV | 能量分数 | 复合奖励 |
|------|---------|----------|----------|
| Baseline | [eval.csv](outputs/exp_sft_rl_v5/TiO2/baseline/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/TiO2/baseline/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/TiO2/baseline/scored/composite_reward.csv) |
| SFT LoRA64 | [eval.csv](outputs/exp_sft_rl_v5/TiO2/sft_lora64/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/TiO2/sft_lora64/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/TiO2/sft_lora64/scored/composite_reward.csv) |
| SFT Full FT | [eval.csv](outputs/exp_sft_rl_v5/TiO2/sft_full_ft/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/TiO2/sft_full_ft/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/TiO2/sft_full_ft/scored/composite_reward.csv) |
| DPO LoRA64 | [eval.csv](outputs/exp_sft_rl_v5/TiO2/dpo_lora64/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/TiO2/dpo_lora64/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/TiO2/dpo_lora64/scored/composite_reward.csv) |
| DPO Full FT | [eval.csv](outputs/exp_sft_rl_v5/TiO2/dpo_full_ft/scored/eval.csv) | [ehull_scores.csv](outputs/exp_sft_rl_v5/TiO2/dpo_full_ft/scored/ehull_scores.csv) | [composite_reward.csv](outputs/exp_sft_rl_v5/TiO2/dpo_full_ft/scored/composite_reward.csv) |

---

## 可视化图表

### LoRA64 分支图表
| 目标 | 能量直方图 | 能量CDF | 稳定性对比 |
|------|-----------|---------|-----------|
| LiFePO4 | [energy_histogram.png](reports/exp_sft_rl_v5/three_way_lora64/LiFePO4/plots/energy_histogram.png) | [energy_cdf.png](reports/exp_sft_rl_v5/three_way_lora64/LiFePO4/plots/energy_cdf.png) | [stability_comparison.png](reports/exp_sft_rl_v5/three_way_lora64/LiFePO4/plots/stability_comparison.png) |
| NaCl | [energy_histogram.png](reports/exp_sft_rl_v5/three_way_lora64/NaCl/plots/energy_histogram.png) | [energy_cdf.png](reports/exp_sft_rl_v5/three_way_lora64/NaCl/plots/energy_cdf.png) | [stability_comparison.png](reports/exp_sft_rl_v5/three_way_lora64/NaCl/plots/stability_comparison.png) |
| TiO2 | [energy_histogram.png](reports/exp_sft_rl_v5/three_way_lora64/TiO2/plots/energy_histogram.png) | [energy_cdf.png](reports/exp_sft_rl_v5/three_way_lora64/TiO2/plots/energy_cdf.png) | [stability_comparison.png](reports/exp_sft_rl_v5/three_way_lora64/TiO2/plots/stability_comparison.png) |

### Full FT 分支图表
| 目标 | 能量直方图 | 能量CDF | 稳定性对比 |
|------|-----------|---------|-----------|
| LiFePO4 | [energy_histogram.png](reports/exp_sft_rl_v5/three_way_full_ft/LiFePO4/plots/energy_histogram.png) | [energy_cdf.png](reports/exp_sft_rl_v5/three_way_full_ft/LiFePO4/plots/energy_cdf.png) | [stability_comparison.png](reports/exp_sft_rl_v5/three_way_full_ft/LiFePO4/plots/stability_comparison.png) |
| NaCl | [energy_histogram.png](reports/exp_sft_rl_v5/three_way_full_ft/NaCl/plots/energy_histogram.png) | [energy_cdf.png](reports/exp_sft_rl_v5/three_way_full_ft/NaCl/plots/energy_cdf.png) | [stability_comparison.png](reports/exp_sft_rl_v5/three_way_full_ft/NaCl/plots/stability_comparison.png) |
| TiO2 | [energy_histogram.png](reports/exp_sft_rl_v5/three_way_full_ft/TiO2/plots/energy_histogram.png) | [energy_cdf.png](reports/exp_sft_rl_v5/three_way_full_ft/TiO2/plots/energy_cdf.png) | [stability_comparison.png](reports/exp_sft_rl_v5/three_way_full_ft/TiO2/plots/stability_comparison.png) |

---

## 实验日志

- [Phase 5 执行日志](logs/exp_sft_rl_v5_phase5_20260304_180416.log) (~214KB)
- [前期实验日志](logs/exp_sft_rl_v5_20260303_144338.log)
- [实验主日志](outputs/exp_sft_rl_v5/experiment.log) (~490KB)

---

## 关键结果摘要

### 稳定性提升 (Best: TiO2 Full FT)
| 目标 | Baseline | SFT | DPO | 提升 |
|------|----------|-----|-----|------|
| TiO2 (Full FT) | 5.10% | 4.68% | **6.07%** | +0.97% ✅ |
| TiO2 (LoRA64) | 5.10% | 4.90% | **5.30%** | +0.20% ✅ |
| NaCl (Full FT) | 5.05% | 4.44% | **4.73%** | -0.32% |
| LiFePO4 (Full FT) | 12.50% | 10.72% | **10.15%** | -2.35% |

### 能量优化 (越低越好)
- LiFePO4: -4.46 → -4.28 eV/atom (DPO Full FT)
- NaCl: -1.96 → -1.97 eV/atom (DPO Full FT)
- TiO2: -5.69 → -5.62 eV/atom (DPO Full FT)

---

*索引文件位置: `EXPERIMENT_INDEX_v5.md`*
