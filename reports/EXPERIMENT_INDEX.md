# DPO-CrystaLLM 实验数据索引

> 最后更新: 2026-02-17
>
> 本文档汇总所有实验配置、报告和数据文件，方便快速查找和记录。

---

## 目录

- [一、总览表格](#一总览表格)
- [二、核心汇总文件](#二核心汇总文件)
- [三、实验详情](#三实验详情)
  - [3.1 主实验 — exp_final_50k（50K 生产实验）](#31-主实验--exp_final_50k50k-生产实验)
  - [3.2 消融实验 — DPO / cDPO / SimPO](#32-消融实验--dpo--cdpo--simpo)
  - [3.3 SFT 实验 — exp_sft_stable](#33-sft-实验--exp_sft_stable)
  - [3.4 SFT+RL 两阶段 — exp_sft_rl_smoke](#34-sftrl-两阶段--exp_sft_rl_smoke)
  - [3.5 Demo8 系列（LiFePO4 / NaCl）](#35-demo8-系列lifepo4--nacl)
  - [3.6 多目标实验](#36-多目标实验)
  - [3.7 早期 / 测试实验](#37-早期--测试实验)
- [四、分析报告](#四分析报告)
- [五、Baseline / 对照实验](#五baseline--对照实验)
- [六、DFT 验证](#六dft-验证)
- [七、论文素材](#七论文素材)
- [八、数据记录区](#八数据记录区)

---

## 一、总览表格

| 实验名称 | 方法 | 目标体系 | 样本量 | 稳定率(%) | 关键结论 | 状态 |
|---|---|---|---|---|---|---|
| exp_final_50k | DPO | LiFePO4 | 50K | 12.12→12.27 (+0.15) | 改善幅度微弱 | ✅ 完成 |
| exp_ablation_dpo | DPO(调参) | LiFePO4 | — | 12.12→12.16 (+0.04) | 低于统计显著性 | ✅ 完成 |
| exp_ablation_cdpo | cDPO | LiFePO4 | — | 12.12→12.14 (+0.02) | 低于统计显著性 | ✅ 完成 |
| exp_ablation_simpo | SimPO | LiFePO4 | — | 12.12→12.14 (+0.02) | 低于统计显著性 | ✅ 完成 |
| exp_sft_stable | SFT | LiFePO4 | — | 12.12→11.03 (-1.1) | 稳定率下降，命中率上升 | ✅ 完成 |
| exp_sft_rl_smoke | SFT+DPO | LiFePO4/NaCl | — | — | 两阶段管线 Smoke Test | ✅ 完成 |
| exp_multi_Li3PS4 | 多目标 | Li3PS4 | — | — | 多目标配置 | ⏳ 待运行 |
| exp_multi_NaCl | 多目标 | NaCl | — | — | 多目标配置 | ⏳ 待运行 |
| exp_multi_TiO2 | 多目标 | TiO2 | — | — | 多目标配置 | ⏳ 待运行 |
| exp_multi_BaTiO3 | 多目标 | BaTiO3 | — | — | 多目标配置 | ⏳ 待运行 |
| exp_smoke_test | DPO | — | — | — | 初始冒烟测试 | ✅ 完成 |
| exp_smoke_test_v2 | DPO | — | — | — | 冒烟测试 v2 | ✅ 完成 |

---

## 二、核心汇总文件

| 文件 | 说明 |
|---|---|
| `reports/all_experiments_summary.csv` | **全部实验主表**：含 validity, stability, energy, training 等指标 |
| `reports/ablation_comparison_delta.csv` | 消融实验 Delta 指标（稳定率差、能量差、损失下降等） |
| `reports/baselines_bon_rejection.csv` | Best-of-N & Rejection Sampling 基线结果 |
| `reports/ablation_deep_analysis.md` | 消融实验深度分析：所有变体 <0.2% 改善 |
| `reports/improvement_plan.md` | 失败原因分析 & 改进策略（空间群分布是关键） |
| `reports/pre_launch_check_50k.md` | 50K 实验预检清单（含 MatGL 解析 bug 修复） |

---

## 三、实验详情

### 3.1 主实验 — exp_final_50k（50K 生产实验）

| 类型 | 路径 |
|---|---|
| 配置 | `experiments/exp_final_50k/config.sh` |
| 报告索引 | `reports/exp_final_50k/index.md` |
| 对比报告 | `reports/exp_final_50k/summary.md` |
| 数据表 | `reports/exp_final_50k/summary.csv` |
| 详细分析(中文) | `reports/exp_final_50k/analysis_50k_detailed.md` |

**关键参数**: TARGET=LiFePO4, NUM_SAMPLES=50000, DPO_STEPS=2000, BETA=0.1, LR=5e-7

**核心结果**: Validity 100%, Stability 12.12%→12.27%, 改善幅度极小

---

### 3.2 消融实验 — DPO / cDPO / SimPO

#### 汇总

| 类型 | 路径 |
|---|---|
| 汇总报告 | `reports/ablation_comparison/ablation_summary.md` |
| 汇总数据 | `reports/ablation_comparison/ablation_results.csv` |
| Delta 对比 | `reports/ablation_comparison_delta.csv` |
| 深度分析 | `reports/ablation_deep_analysis.md` |

#### exp_ablation_dpo

| 类型 | 路径 |
|---|---|
| 配置 | `experiments/exp_ablation_dpo/config.sh` |
| 报告 | `reports/exp_ablation_dpo/summary.md` |
| 数据 | `reports/exp_ablation_dpo/summary.csv` |

**参数**: DPO_STEPS=8000, BETA=2.5, LR=1e-7, PAIR_MAX=15000

#### exp_ablation_cdpo

| 类型 | 路径 |
|---|---|
| 配置 | `experiments/exp_ablation_cdpo/config.sh` |
| 报告 | `reports/exp_ablation_cdpo/summary.md` |
| 数据 | `reports/exp_ablation_cdpo/summary.csv` |

#### exp_ablation_simpo

| 类型 | 路径 |
|---|---|
| 配置 | `experiments/exp_ablation_simpo/config.sh` |
| 报告 | `reports/exp_ablation_simpo/summary.md` |
| 数据 | `reports/exp_ablation_simpo/summary.csv` |

---

### 3.3 SFT 实验 — exp_sft_stable

| 类型 | 路径 |
|---|---|
| 配置 | `experiments/exp_sft_stable/config.sh` |
| 报告索引 | `reports/exp_sft_stable/index.md` |
| 对比报告 | `reports/exp_sft_stable/summary.md` |
| 数据表 | `reports/exp_sft_stable/summary.csv` |

**核心结果**: Stability 12.12%→11.03% (-1.1%), 组分命中率有所提升

---

### 3.4 SFT+RL 两阶段 — exp_sft_rl_smoke

| 类型 | 路径 |
|---|---|
| 配置 | `experiments/exp_sft_rl_smoke/config.sh` |
| 运行脚本 | `experiments/exp_sft_rl_smoke/run.sh` |
| 管线报告 | `reports/exp_sft_rl_smoke/sft_rl_summary.md` |
| 三方对比汇总 | `reports/exp_sft_rl_smoke/three_way/three_way_summary.csv` |
| LiFePO4 三方对比 | `reports/exp_sft_rl_smoke/three_way/LiFePO4/three_way_comparison.md` |
| NaCl 三方对比 | `reports/exp_sft_rl_smoke/three_way/NaCl/three_way_comparison.md` |

---

### 3.5 Demo8 系列（LiFePO4 / NaCl）

| 类型 | 路径 |
|---|---|
| Demo8 索引 | `reports/demo8_index.md` |
| 正式实验报告 | `reports/demo8_results_formal_writeup.md` |
| LiFePO4 结论 | `reports/demo8_LiFePO4_conclusion.md` |
| NaCl 结论 | `reports/demo8_NaCl_trimmed_conclusion.md` |
| 结果压缩包 | `reports/demo8_results_packet.zip` |

**LiFePO4 关键结果**: DPO 改善 mean -1.30 eV/atom, median -0.31 eV/atom

---

### 3.6 多目标实验

| 实验 | 配置路径 | 状态 |
|---|---|---|
| exp_multi_Li3PS4 | `experiments/exp_multi_Li3PS4/config.sh` | ⏳ 待运行 |
| exp_multi_NaCl | `experiments/exp_multi_NaCl/config.sh` | ⏳ 待运行 |
| exp_multi_TiO2 | `experiments/exp_multi_TiO2/config.sh` | ⏳ 待运行 |
| exp_multi_BaTiO3 | `experiments/exp_multi_BaTiO3/config.sh` | ⏳ 待运行 |

---

### 3.7 早期 / 测试实验

| 实验 | 配置路径 | 说明 |
|---|---|---|
| exp_smoke_test | `experiments/exp_smoke_test/config.sh` | 初始冒烟测试 |
| exp_smoke_test_v2 | `experiments/exp_smoke_test/config.sh` | 冒烟测试 v2 |
| exp_20260203_LiFePO4 | `experiments/exp_20260203_180121_LiFePO4/config.sh` | 早期 LiFePO4 |
| exp_20260204_LiFePO4_test | `experiments/exp_20260204_132341_LiFePO4_test/config.sh` | LiFePO4 测试 |
| exp_20260204_LiFePO4_fixed | `experiments/exp_20260204_165505_LiFePO4_fixed/config.sh` | LiFePO4 修复版 |
| exp_20260206_LiFePO4 | `reports/exp_20260206_171427_LiFePO4/index.md` | 早期报告 |
| exp_LiFePO4_prod_ready | `experiments/exp_LiFePO4_prod_ready/config.sh` | 生产就绪版 |

---

## 四、分析报告

| 报告 | 路径 | 说明 |
|---|---|---|
| 偏好对质量分析 | `reports/pair_quality_analysis/pair_quality_report.md` | 5000 对偏好数据质量分析 |
| 偏好对统计 | `reports/pair_quality_analysis/pair_stats_detailed.json` | 详细统计 JSON |
| 结构多样性分析 | `reports/structure_analysis_baseline/structure_analysis_report.md` | 空间群分布、晶系、晶格参数 |
| 结构统计 | `reports/structure_analysis_baseline/baseline_structure_stats.json` | 基线结构统计 JSON |

---

## 五、Baseline / 对照实验

| 报告 | 路径 | 说明 |
|---|---|---|
| 基线方法对比 | `reports/baselines_comparison/baselines_report.md` | Best-of-N & Rejection Sampling 详细对比 |
| BoN 结果 | `reports/baselines_comparison/bon_results.json` | Best-of-N JSON 数据 |
| Rejection 结果 | `reports/baselines_comparison/rejection_results.json` | Rejection Sampling JSON 数据 |
| 汇总 CSV | `reports/baselines_bon_rejection.csv` | 稳定率 & GPU 效率汇总 |

**关键发现**: K=100 时 BoN 稳定率可达 100%，但 GPU 开销极高

---

## 六、DFT 验证

| 类型 | 路径 | 说明 |
|---|---|---|
| 准备文档 | `reports/dft_validation_baseline/dft_validation_prep.md` | DFT 验证准备说明 |
| 候选结构 | `reports/dft_validation_baseline/selected_structures.csv` | Top-20 结构（Ehull proxy 排序） |
| CIF 文件 | `reports/dft_validation_baseline/selected_cifs/` | 20 个 CIF 文件 |
| POSCAR 文件 | `reports/dft_validation_baseline/poscar/` | 20 个 VASP POSCAR 输入 |
| QE 输入 | `reports/dft_validation_baseline/qe_inputs/` | 20 个 Quantum ESPRESSO 输入 |
| 结果模板 | `reports/dft_validation_baseline/dft_results_template.csv` | DFT 结果记录模板 |

---

## 七、论文素材

| 类型 | 路径 | 说明 |
|---|---|---|
| Table 1 | `reports/paper_figures/tab1_main_results.tex` | 主结果 LaTeX 表格 |

---

## 八、数据记录区

> 在下方记录新实验数据、待办事项和备注。

### 待记录实验

| 日期 | 实验名称 | 方法 | 目标体系 | 结果摘要 | 备注 |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |

### 待办事项

- [ ] 多目标实验（Li3PS4 / NaCl / TiO2 / BaTiO3）待运行和记录
- [ ] DFT 验证结果待填入 `dft_results_template.csv`
- [ ] 论文图表素材补充

### 备注

```
（在此添加自由备注）
```
