---
name: DPO-CrystaLLM 科研路线图
overview: 基于 50K 实验的 negative result，设计一套从超参数验证、系统性消融、多材料泛化到 DFT 验证的完整科研路线，目标产出一篇高质量 AI4Science 论文。
todos:
  - id: phase1-ablation
    content: "Phase 1.1: 运行 run_ablation_suite.sh 执行三组消融实验 (DPO/cDPO/SimPO)，验证 beta=2.5 是否产生显著改善"
    status: in_progress
  - id: phase1-beta-sweep
    content: "Phase 1.2: 新增 run_beta_sweep.sh 脚本，在 10K 样本上对 beta={0.1,0.5,1.0,2.0,2.5,5.0,10.0} 做系统性扫描"
    status: in_progress
  - id: phase1-pair-analysis
    content: "Phase 1.3: 新增偏好对质量分析功能 — gap 分布、token 长度相关性、策略对比"
    status: pending
  - id: phase2-factor-ablation
    content: "Phase 2.1: 因素拆解消融 — 偏好对数量/训练步数/LoRA vs Full/Gap 阈值/MAX_TOKENS"
    status: pending
  - id: phase2-baselines
    content: "Phase 2.3: 新增 Best-of-N 和 Rejection Sampling 基线对比脚本"
    status: pending
  - id: phase3-multi-material
    content: "Phase 3: 多材料泛化实验 — NaCl, TiO2, BaTiO3, Li3PS4"
    status: pending
  - id: phase4-structure-analysis
    content: "Phase 4.1: 新增结构多样性分析脚本 — 空间群分布、晶格参数、配位环境"
    status: pending
  - id: phase4-novelty
    content: "Phase 4.2: 配置 TRAINING_DATA_DIR，启用新颖性评估"
    status: pending
  - id: phase4-dft
    content: "Phase 4.3: 对 top-20 DPO 生成结构做 DFT 验证"
    status: pending
  - id: phase5-paper
    content: "Phase 5: 生成论文所需的全部图表，撰写论文"
    status: pending
isProject: false
---

# DPO-CrystaLLM 下一步科研计划

## 当前状态总结

50K 大实验表明：在 beta=0.1, lr=5e-7, 2000 步, 5000 偏好对的配置下，DPO 对齐效果几乎为零（稳定率仅提升 +0.15%）。根因分析指向 beta 过低（KL 正则化过强）为首要瓶颈。三组消融实验已配置就绪但尚未运行。

---

## 第一阶段：验证 DPO 有效性（最高优先级，~3-5 天）

**目标**：证明 DPO 在正确超参数下能显著改善晶体生成质量。

### 1.1 运行已配置的三组消融实验

直接执行 `scripts/run_ablation_suite.sh`，复用 50K baseline 数据：

- **Ablation A** (`exp_ablation_dpo`): 标准 DPO, beta=2.5, lr=1e-7, 8000 步, 15000 对
- **Ablation B** (`exp_ablation_cdpo`): cDPO + label smoothing=0.1
- **Ablation C** (`exp_ablation_simpo`): SimPO (无参考模型), beta=2.0, gamma=1.0

**预期产出**：如果 beta=2.5 有效，应看到稳定率提升 >2% 和中位能量改善 >0.05 eV/atom。

### 1.2 beta 敏感性扫描（关键贡献点）

在 **10K 样本规模** 上做快速扫描（节省 5x 计算），测试 beta = {0.1, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0}：

- 需要新增脚本 `scripts/run_beta_sweep.sh`
- 复用 exp_final_50k 的 baseline 数据（随机抽样 10K 做重采样评估）
- 每个 beta 值：pair building + DPO training + 10K resampling + scoring
- 每轮约 6-8 小时，7 个值 = ~50 小时

**预期产出**：beta vs. stability_rate 曲线图 —— 这是论文中非常有价值的图表，展示 DPO 在晶体生成领域的超参数敏感性特征，区别于 NLP 领域的典型 beta 范围（0.1-0.5）。

### 1.3 偏好对质量分析

在 [scripts/41_build_pairs_with_token_filter.py](scripts/41_build_pairs_with_token_filter.py) 基础上新增分析：

- 偏好对的能量 gap 分布直方图
- token 长度 vs. 能量质量的相关性分析
- trimmed vs. untrimmed 策略的偏好对质量对比
- 输出偏好对覆盖率统计（多少 unique prompt 被覆盖）

---

## 第二阶段：系统性消融研究（~1-2 周）

**目标**：构建完整的消融表格，阐明各因素的贡献。

### 2.1 因素拆解消融

在最佳 beta 基础上，逐一控制变量：


| 实验  | 变化因素                                      | 其他保持最优                    |
| --- | ----------------------------------------- | ------------------------- |
| F1  | 偏好对数量: 2K vs 5K vs 10K vs 15K             | beta=best, lr=1e-7, 8000步 |
| F2  | 训练步数: 2K vs 4K vs 8K vs 16K               | beta=best, pairs=15K      |
| F3  | LoRA vs 全参微调                              | beta=best, best config    |
| F4  | Gap 阈值: 0.05 vs 0.1 vs 0.2 vs 0.5 eV/atom | beta=best                 |
| F5  | MAX_TOKENS: 1024 vs 1280 vs 1536          | beta=best                 |


使用 10K 评估样本，每组约 6 小时，总计 ~90 小时。

### 2.2 损失函数对比（已部分包含在 1.1）

- DPO vs. cDPO vs. SimPO 在最优超参数下的公平对比
- 训练曲线对比（loss, advantage, gradient norm）
- 收敛速度对比

### 2.3 对比基线方法

新增两个重要基线（不需要训练，只需后处理）：

- **Best-of-N Sampling**：从 baseline 50K 样本中按能量排序取 top-K，计算等效稳定率
- **Rejection Sampling**：设定能量阈值过滤，统计需要多少样本才能达到 DPO 的稳定率

这两个基线实现简单（纯 Python 后处理脚本），但对论文至关重要 —— 如果 DPO 不能超越 Best-of-N，则方法学贡献有限。

---

## 第三阶段：多材料泛化实验（~2 周）

**目标**：证明方法不是 LiFePO4-specific，具有通用性。

### 3.1 选择 3-4 个代表性目标材料

建议选择结构多样性好的体系：


| 材料         | 晶系                  | 应用领域  | Z 值   |
| ---------- | ------------------- | ----- | ----- |
| **NaCl**   | 立方 (rock-salt)      | 基准体系  | 4     |
| **TiO2**   | 四方 (rutile/anatase) | 光催化   | 2 或 4 |
| **BaTiO3** | 钙钛矿                 | 铁电/压电 | 1     |
| **Li3PS4** | 正交                  | 固态电解质 | 4     |


### 3.2 每个材料运行完整流水线

使用 `scripts/run_multi_target.sh`，对每个目标使用第一阶段确定的最优超参数：

```
TARGETS="NaCl,TiO2,BaTiO3,Li3PS4" bash scripts/run_multi_target.sh
```

每个材料 ~48 小时（50K baseline + DPO），4 个材料 ~8 天（可串行）。

### 3.3 跨材料一致性分析

- 各材料的稳定率提升幅度对比
- 各材料的最优 beta 是否一致
- 材料复杂度（原子数/元素数）vs. DPO 改善效果的关系

---

## 第四阶段：深度分析和验证（~1 周）

### 4.1 结构多样性分析（新增脚本）

新增 `scripts/38_analyze_structures.py`：

- 生成结构的空间群分布对比（baseline vs DPO）
- 晶格参数 (a, b, c, alpha, beta, gamma) 分布
- 配位环境统计
- 使用 pymatgen StructureMatcher 计算结构多样性

### 4.2 新颖性评估（修复现有功能）

- 配置 `TRAINING_DATA_DIR` 指向 CrystaLLM 训练集
- 运行 [scripts/37_compute_novelty.py](scripts/37_compute_novelty.py) 计算新颖性
- 分析 DPO 是否仅"记忆"训练集中的稳定结构，还是生成了真正新颖的稳定结构

### 4.3 DFT 验证（论文核心亮点）

- 从 DPO 模型生成的稳定结构中挑选 top-20（按 Ehull 排序）
- 对每个结构做 VASP/Quantum ESPRESSO 结构优化
- 对比 MatGL proxy 能量 vs. DFT 能量
- 验证 proxy 排序是否与 DFT 排序一致（Spearman/Kendall 相关系数）
- **这是审稿人最关心的验证环节**

### 4.4 Proxy 信号质量评估

- 随机抽取 100 个结构，同时用 MatGL 和 MACE/CHGNet 评分
- 计算不同 proxy 之间的排序一致性
- 分析 proxy 误导偏好对构建的风险

---

## 第五阶段：论文撰写所需的关键图表


| 图/表   | 内容                                                            | 阶段产出   |
| ----- | ------------------------------------------------------------- | ------ |
| Fig.1 | 方法流程图：Baseline → Scoring → Pair Construction → DPO → Resample | 已有数据   |
| Fig.2 | beta 敏感性曲线：beta vs stability_rate                             | 阶段 1.2 |
| Fig.3 | 能量分布对比：Baseline vs DPO (best config) histogram + CDF          | 阶段 1.1 |
| Fig.4 | 消融热力图：factors vs metrics                                      | 阶段 2.1 |
| Fig.5 | 多材料结果对比：grouped bar chart                                     | 阶段 3   |
| Fig.6 | DFT vs MatGL 相关性散点图                                           | 阶段 4.3 |
| Tab.1 | 主实验结果：Baseline/DPO/cDPO/SimPO/Best-of-N                       | 阶段 1+2 |
| Tab.2 | 多材料泛化结果                                                       | 阶段 3   |
| Tab.3 | DFT 验证结果                                                      | 阶段 4.3 |


---

## 预计论文亮点和贡献

1. **方法贡献**：首次将 DPO 对齐方法应用于晶体结构语言模型，提出基于 ML 力场 proxy 的偏好对自动构建策略
2. **经验发现**：揭示 DPO beta 在材料生成领域需要远高于 NLP 的典型值（2.0-5.0 vs 0.1-0.5），提供理论解释（token 级 log-prob 的幅度差异）
3. **Negative result 价值**：系统性记录 beta=0.1 的失败案例及根因分析，对社区有警示价值
4. **多材料泛化**：证明方法在多种晶体体系上的通用性
5. **DFT 验证**：通过第一性原理计算验证生成结构的真实稳定性

---

## 实施优先级和时间线


| 周次       | 任务                    | 依赖                 |
| -------- | --------------------- | ------------------ |
| Week 1   | 运行三组消融 + beta 扫描      | 无                  |
| Week 2   | 因素拆解消融 + Best-of-N 基线 | Week 1 结果确认 DPO 有效 |
| Week 3-4 | 多材料实验                 | Week 2 确定最优配置      |
| Week 5   | 结构分析 + 新颖性 + DFT 验证   | Week 3-4           |
| Week 6-7 | 论文撰写                  | All                |


