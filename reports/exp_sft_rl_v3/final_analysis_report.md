# exp_sft_rl_v3 最终分析报告（2026-02-24）

## 1. 实验概况

- 实验名：`exp_sft_rl_v3`
- 目标组分：`LiFePO4`、`NaCl`、`TiO2`
- 每目标采样数：2000
- 分支：`full_ft`、`lora64`
- DPO 配置：`steps=2000`，`lr=1e-7`，`loss=dpo`，`beta=2.5`
- 奖励权重：`E/S/D/C = 0.4/0.2/0.2/0.2`
- 运行状态：Pipeline 全部完成（Phase 1~6，exit code=0）

数据来源：
- `reports/exp_sft_rl_v3/sft_rl_summary.md`
- `reports/exp_sft_rl_v3/three_way_full_ft/three_way_summary.csv`
- `reports/exp_sft_rl_v3/three_way_lora64/three_way_summary.csv`
- 各 target 的 `three_way_comparison.md`

---

## 2. 结果总览（稳定率与能量）

### 2.1 Stability Rate（越高越好）

| Target | Branch | Baseline | SFT | DPO | DPO-Baseline |
|---|---:|---:|---:|---:|---:|
| LiFePO4 | full_ft | 0.1250 | 0.1260 | 0.1240 | -0.0010 |
| NaCl | full_ft | 0.0505 | 0.0495 | 0.0485 | -0.0020 |
| TiO2 | full_ft | 0.0510 | 0.0500 | 0.0510 | +0.0000 |
| LiFePO4 | lora64 | 0.1250 | 0.1240 | 0.1240 | -0.0010 |
| NaCl | lora64 | 0.0505 | 0.0505 | 0.0505 | +0.0000 |
| TiO2 | lora64 | 0.0510 | 0.0485 | 0.0490 | -0.0020 |

结论：本次配置下，两个分支都没有在稳定率上超过 baseline；平均来看，DPO 相对 baseline 约 `-0.001`（-0.10 个百分点）。

### 2.2 Mean MatGL Energy（eV/atom，越低越好）

| Target | Branch | Baseline | SFT | DPO | DPO-Baseline |
|---|---:|---:|---:|---:|---:|
| LiFePO4 | full_ft | -4.4646 | -4.4749 | -4.4333 | +0.0313 |
| NaCl | full_ft | -1.9610 | -1.9521 | -1.9508 | +0.0102 |
| TiO2 | full_ft | -5.6891 | -5.7308 | -5.7320 | -0.0430 |
| LiFePO4 | lora64 | -4.4646 | -4.4757 | -4.4584 | +0.0061 |
| NaCl | lora64 | -1.9610 | -1.9598 | -1.9602 | +0.0008 |
| TiO2 | lora64 | -5.6891 | -5.6907 | -5.7011 | -0.0121 |

结论：`TiO2` 上能量有改善（尤其 full_ft），但 `LiFePO4` 和 `NaCl` 上 DPO 后均值能量未改善，和稳定率结论一致。

---

## 3. 分支对比与解读

### 3.1 Full FT 分支

- `LiFePO4`：SFT 小幅提升稳定率（+0.0010），但 DPO 回落到 0.1240。
- `NaCl`：SFT 与 DPO 都低于 baseline（最终 -0.0020）。
- `TiO2`：稳定率与 baseline 持平（0.0510），但能量均值有较明显改善（-0.0430 eV/atom）。
- 说明：该分支更偏向优化能量分布尾部/均值，但没有转化为稳定率增益。

### 3.2 LoRA64 分支

- `LiFePO4`：SFT、DPO 均略低于 baseline（-0.0010）。
- `NaCl`：基本与 baseline 持平。
- `TiO2`：DPO 后仍低于 baseline（-0.0020），但较 SFT 有轻微恢复（0.0485 -> 0.0490）。
- 说明：LoRA64 更稳，但在本批数据规模和超参下，收益不足以拉高稳定率。

---

## 4. 关键现象与可能原因

1. **稳定率进入“平台区”**  
   三个目标的 baseline 稳定率分别约为 12.5%、5.05%、5.10%，在 2000 样本规模下，DPO 的改善空间有限，统计涨跌幅集中在 0.0%~0.2% 量级。

2. **能量优化与稳定率不完全一致**  
   例如 `TiO2` 能量均值改善明显，但稳定率几乎不变，说明“平均能量下降”并不必然带来 `Ehull < 0.05` 样本数增加。

3. **奖励维度有效但目标转化有限**  
   从 three-way 细项看，`R_composition` 普遍提升，`R_structure` 均值稳定在 0.5（rank 归一化特征），但最终主指标（稳定率）未得到同步提升。

4. **Ehull 参考使用了 fallback（无 MP API）**  
   日志存在 `MP_API_KEY not set` 提示；当前 Ehull 评估依赖 fallback hull 参考，可能对“稳定/不稳定”边界判定精度有影响。

---

## 5. 结论

本次 `exp_sft_rl_v3` 在“流程正确性与可运行性”上已达标（完整跑通、无中断、产物齐全），但在“效果增益”上，**尚未验证出 DPO 对稳定率的稳定正提升**。  
在当前设置下，更合理的结论是：

- Pipeline 已可用于批量实验与对比；
- 但这组超参和样本规模不足以支持“DPO 明显优于 baseline”的结论；
- 下一步需要把重点从“修 bug”转为“提升统计显著性与 reward-to-metric 转化效率”。

---

## 6. 下一步建议（按优先级）

1. **扩大样本规模再复验**  
   将每目标采样从 2000 提升到 10000+，优先验证稳定率差异是否具有统计显著性。

2. **做 DPO 超参网格**  
   至少扫描 `beta`（如 1.0/2.5/5.0）与学习率（5e-8/1e-7/2e-7），并固定同一随机种子组做公平对比。

3. **加强 reward 与主指标一致性**  
   对比不同 reward 组合（例如提高 energy 权重，或在 pair 构建时引入更严格 gap）看稳定率响应曲线。

4. **启用 MP API 进行 Ehull 校准复评**  
   对 top-k 样本做 API 版 Ehull 复核，确认 fallback 判定是否引入系统偏差。

5. **优先保留 LoRA 作为主线**  
   当前 full_ft 未表现出稳定的主指标优势，后续可先围绕 LoRA 路线做更密集调参。

