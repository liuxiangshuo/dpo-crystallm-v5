# SFT + RL Pipeline (Modular Version)

这是模块化重构后的pipeline版本。原 `run_sft_rl_pipeline.sh` (1671行) 被拆分为更小、更易维护的模块。

## 目录结构

```
scripts/pipeline/
├── README.md              # 本文件
├── run_pipeline_v2.sh     # 新主入口脚本
├── header.sh              # 配置、conda初始化、目录设置
├── footer.sh              # 最终报告生成
├── lib/                   # 共享函数库
│   ├── logging.sh         # 错误日志和计时函数
│   ├── validation.sh      # Phase验证函数
│   ├── helpers.sh         # 通用辅助函数
│   ├── phase1_funcs.sh    # Phase 1专用函数
│   ├── phase2_funcs.sh    # Phase 2专用函数
│   ├── phase3_funcs.sh    # Phase 3专用函数
│   ├── phase4_funcs.sh    # Phase 4专用函数
│   └── phase5_funcs.sh    # Phase 5专用函数
└── phases/                # 各Phase执行脚本
    ├── phase1.sh          # 多组分基线生成+打分
    ├── phase2.sh          # SFT训练
    ├── phase3.sh          # SFT重采样+配对构建
    ├── phase4.sh          # DPO训练
    ├── phase5.sh          # 最终评估+对比报告
    └── phase6.sh          # 结构可视化
```

## 使用方法

与原脚本相同，只是入口改为 `run_pipeline_v2.sh`:

```bash
# 1. 加载配置
source experiments/exp_sft_rl/config.sh

# 2. 运行pipeline
bash scripts/run_pipeline_v2.sh              # 全新运行
RESUME=1 bash scripts/run_pipeline_v2.sh     # 从checkpoint恢复
CLEAN=1 bash scripts/run_pipeline_v2.sh      # 强制清理重新运行
```

## 与原脚本的对比

| 特性 | 原脚本 | 模块化版本 |
|------|--------|-----------|
| 代码行数 | 1671行 | 主入口~80行，各模块平均~150行 |
| 可维护性 | 单文件难以维护 | 分模块易于定位问题 |
| 调试 | 难以隔离特定Phase | 可单独测试各Phase |
| 复用性 | 函数混杂 | 清晰的lib/目录结构 |

## 迁移指南

原有实验配置完全兼容，只需改一下入口脚本名：

```bash
# 旧方式
bash scripts/run_sft_rl_pipeline.sh

# 新方式 (模块化)
bash scripts/run_pipeline_v2.sh
```

## 模块说明

### header.sh
- Conda环境初始化
- 必需变量检查 (EXP_NAME, TARGETS等)
- 默认参数设置
- 目录结构创建

### lib/logging.sh
- `log_error()`: 记录错误到JSONL
- `record_timing()`: 记录Phase执行时间
- 配置快照保存
- 主日志重定向

### lib/validation.sh
- `can_resume_phase()`: 检查Phase是否可以恢复
- `validate_phase1()`: Phase 1数据验证
- `validate_phase2()`: Phase 2输出验证
- `validate_phase3()`: Phase 3数据验证
- `validate_phase4()`: Phase 4输出验证
- `validate_phase5()`: Phase 5报告验证

### lib/helpers.sh
- `check_reward_spread()`: 检查奖励分布
- `merge_eval_csv()`: 合并labels和ehull分数
- `count_csv_rows()`: 统计CSV行数
- `count_scored_rows()`: 统计有效分数行数
- `count_cif_files()`: 统计CIF文件数
- `check_score_fail_rate()`: 检查打分失败率
- `warn_if_no_visualizations()`: 检查可视化输出
- `build_prompt()`: 构建CIF格式prompt

### phases/*.sh
每个Phase文件专注于单一职责：
- 记录开始时间
- 执行Phase特有逻辑
- 质量门控检查
- 调用mark_step_done()
