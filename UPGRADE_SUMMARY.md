# DPO-CrystaLLM 流水线升级总结

## 修改目标
将流水线从"能跑"升级到"能稳定产出可训练 pairs 并完成 DPO 对比报告"。

## 核心改进

### A. 生成阶段质量闸门 (scripts/40_generate_cifs_crystallm.py)

#### A1: 结构级别严格校验
- **新增函数**: `validate_structure()` - 使用 pymatgen 进行结构校验
  - 检查 data_ 块存在性
  - 验证晶格参数（长度 > 0，角度在 (0, 180)）
  - 验证原子坐标（有限数，可 wrap 到 [0,1)）
  - 检查 site 数量（2~300，可配置）
  - 过滤高重复率垃圾内容
- **质量日志输出**:
  - `outputs/exp_*/baseline/quality/validity_detail.jsonl` - 每个样本的详细记录
  - `outputs/exp_*/baseline/quality/summary.json` - 成功率统计和失败原因
  - 每 50 个样本输出进度和 top-3 失败原因

#### A2: 自适应采样回退策略
- **重试机制**: 每个样本最多重试 `MAX_RETRIES` 次（默认 5）
- **参数回退**:
  - attempt 1: 使用原始参数（TOP_K, TEMPERATURE）
  - attempt 2+: 温度降低 20%（下限 0.6），top_k 减半（下限 5）
- **记录**: 每个样本的实际采样参数记录到 validity_detail.jsonl

### B. MatGL 评分稳定性 (scripts/35_score_dir_matgl.py)

#### B1: 结构修复与降级策略
- **新增函数**: `repair_structure()` - 修复结构以提高 MatGL 兼容性
  - Niggli 约化（get_reduced_structure）
  - 坐标 wrap 到 [0,1)
  - 移除问题属性（oxidation_state, magmom, charge）
- **失败记录**:
  - `scores_failed.csv` - 记录所有失败项（含错误类型和 traceback）
  - 失败原因统计输出到控制台
- **不中断**: 单个 CIF 失败不影响整体评分流程

#### B2: LD_LIBRARY_PATH 强制修复
- **入口修复**: 在 import matgl 之前检查 `MATGL_FIX_LD_LIBRARY_PATH=1`
- **自动设置**: 如果启用，自动设置 `LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"`

### C. 配对最低保障 (scripts/41_build_pairs_with_token_filter.py)

#### C1: 最低保障策略
- **新增参数**:
  - `--pair_min_per_prompt` (默认 1): 每个 prompt 至少产出对数
  - `--pair_max_per_prompt` (默认 20): 每个 prompt 最多产出对数（避免垄断）
- **回退机制**: 当 trimmed 策略产出不足时，自动使用 best vs worst 配对
- **统计输出**: `pair_stats.json` 记录每个 prompt 的产出分布

### D. Driver 成功条件检查 (scripts/demo8_dpo_driver.sh)

#### D1: 硬性检查点
- **Step 2.1**: 生成后检查 `MIN_VALID_CIFS`（默认 100）
- **Step 2.5**: 打分后检查 `MIN_SCORED_CIFS`（默认 80）
- **Step 3**: 配对后检查 `MIN_PAIRS`（默认 500）
- **失败快返**: 不满足条件立即退出并提示检查路径

### E. 生产就绪实验配置

#### E1: exp_LiFePO4_prod_ready
- **位置**: `experiments/exp_LiFePO4_prod_ready/`
- **参数设置**:
  - `NUM_SAMPLES=2000` - 足够样本量
  - `TOP_K=20, TEMPERATURE=0.8` - 平衡探索/利用
  - `MAX_RETRIES=5` - 允许重试
  - `MIN_VALID_CIFS=200` - 目标 20% 有效率
  - `MIN_SCORED_CIFS=150` - 目标 80% 评分成功率
  - `MIN_PAIRS=500` - 用户要求
  - `DPO_STEPS=500` - 短跑验证

## 修改文件清单

1. **scripts/40_generate_cifs_crystallm.py**
   - 新增 `validate_structure()` 函数
   - 新增 `extract_first_data_block()` 函数
   - 修改主循环：增加重试机制、结构校验、质量日志、自适应回退

2. **scripts/35_score_dir_matgl.py**
   - 新增 `repair_structure()` 函数
   - 修改主循环：增加结构修复、失败记录
   - 入口增加 LD_LIBRARY_PATH 修复

3. **scripts/41_build_pairs_with_token_filter.py**
   - 新增 `--pair_min_per_prompt` 和 `--pair_max_per_prompt` 参数
   - 修改配对逻辑：按 prompt 分组、最低保障、统计输出

4. **scripts/demo8_dpo_driver.sh**
   - 新增环境变量默认值（MAX_RETRIES, MIN_VALID_CIFS, etc.）
   - 新增 Step 2.1, 2.5, 3 的硬性检查
   - 传递配对参数到配对脚本

5. **experiments/exp_LiFePO4_prod_ready/config.sh** (新建)
   - 生产就绪配置，含详细注释

6. **experiments/exp_LiFePO4_prod_ready/run.sh** (从模板复制)
   - 标准实验运行脚本

## 预期效果

### 质量指标目标
- **valid_parse_rate >= 20%**: 通过结构校验和重试机制
- **matgl_score_success_rate >= 80%**: 通过结构修复和降级策略
- **pairs_A >= 500**: 通过最低保障策略和足够样本量

### 可观测性
- 每个步骤都有详细的日志和统计
- 失败原因可追溯（validity_detail.jsonl, scores_failed.csv, pair_stats.json）
- 进度实时输出（每 50 个样本）

## 运行方式

```bash
cd experiments/exp_LiFePO4_prod_ready
bash run.sh
```

实验日志将输出到 `outputs/exp_*/experiment.log`，各步骤的详细统计在相应子目录中。

## 注意事项

1. **依赖**: 需要 pymatgen 用于结构校验（已在脚本中处理缺失情况）
2. **环境变量**: 确保 `MAX_RETRIES` 等变量在 config.sh 中正确设置
3. **路径**: 确保 `CRYSTALLM_CKPT_DIR` 和 `CRYSTALLM_PKG_DIR` 路径正确
4. **Conda 环境**: 需要 myenv, matgl_env, dpo_crystallm 环境

## 下一步

运行实验并检查：
1. `outputs/exp_*/baseline/quality/summary.json` - 生成质量统计
2. `outputs/exp_*/baseline/scored/scores_failed.csv` - MatGL 失败记录
3. `outputs/exp_*/pairs/pair_stats.json` - 配对统计
4. `reports/exp_*/summary.md` - 最终对比报告
