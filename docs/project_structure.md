# 项目结构

> 自动生成于 2026-05-07 05:24:10

```
Spiderette Strategy Lab/
├── docs/  (5 files)  # 项目文档（sync_docs.py 自动生成）
│   ├── api.md  # API 端点列表（自动生成）
│   ├── meta.json  # 项目元数据（模块/策略/端点统计）
│   ├── modules.md  # 模块地图（自动生成）
│   ├── project_structure.md
│   └── strategies.md  # 策略列表（自动生成）
├── experiments/  # 实验配置与结果
│   ├── configs/  # 实验配置文件（TOML 格式）
│   └── results/  (6 files)  # 实验输出结果
│       ├── benchmark_report.json
│       ├── benchmark_results.csv
│       ├── benchmark_summary.txt
│       ├── neural_model.npz
│       ├── report.md
│       └── strategy_profile_20260504_010555.txt
├── iterations/  # 策略迭代记录（每次迭代自动存档）
├── logs/  (4 files)  # 运行日志（自动轮转，按大小归档）
│   ├── app.log  # 应用主日志（INFO 级别）
│   ├── error.log  # 错误日志（WARNING 级别以上）
│   ├── strategy.log  # 策略执行日志（DEBUG 级别）
│   └── training.log  # 训练日志（RL/遗传算法）
├── manifests/  (1 files)  # 自定义策略清单
│   └── custom_mcts_v2.json  # 自定义 MCTS 变体配置
├── models/  # 训练好的模型文件（.npz/.pkl）
├── src/  (1 files, 10,257 lines)  # 核心源码
│   ├── analysis/  (16 files, 3,836 lines)  # Layer 3: 分析层（指标 + 报告 + 遗传算法 + 锦标赛）
│   │   ├── metrics/
│   │   ├── optimization/
│   │   ├── research/
│   │   ├── __init__.py
│   │   ├── batch.py  # 批量模拟引擎（多进程并行）
│   │   ├── compare.py  # 策略对比分析（统计检验）
│   │   ├── exporter.py  # 结果导出（JSON/CSV/Markdown）
│   │   ├── factor.py  # 8 维决策因子计算
│   │   ├── genetic.py  # 遗传算法参数优化
│   │   ├── metrics.py  # 量化指标体系（胜率/置信区间/效应量）
│   │   ├── pattern.py  # 决策模式挖掘
│   │   ├── profile.py  # 策略画像生成（8 维雷达图数据）
│   │   ├── report.py  # 报告生成器（Markdown/HTML）
│   │   ├── runner.py  # 基准测试运行器（同 seed 公平对比）
│   │   ├── scenario.py  # 场景分析（特定牌局深度分析）
│   │   ├── tournament.py  # 锦标赛模式（多策略循环赛）
│   │   ├── tuning.py  # 超参数调优（网格/随机/贝叶斯）
│   │   ├── utils.py  # 分析工具函数（统计/格式化）
│   │   └── weakness.py  # 弱点检测（基于因子偏差）
│   ├── core/  (7 files, 1,105 lines)  # Layer 1: 核心层（不可变类型 + 规则引擎）
│   │   ├── __init__.py
│   │   ├── exceptions.py  # 自定义异常层次
│   │   ├── info_set.py  # 信息集管理（隐藏牌推断 + 确定化采样）
│   │   ├── manifest.py  # 策略清单解析（JSON → StrategyManifest）
│   │   ├── rules.py  # 规则引擎（合法移动 + 状态转移）
│   │   ├── session.py  # 游戏会话管理（状态机 + 回调）
│   │   └── types.py  # 不可变游戏状态（frozen dataclass）
│   ├── envs/  (3 files, 176 lines)  # Layer 2: 环境层（模拟器 + 牌局生成）
│   │   ├── plugins/  (1 files)
│   │   │   └── __init__.py
│   │   ├── __init__.py
│   │   ├── generator.py  # 牌局生成器（种子控制 + 难度分级）
│   │   └── simulator.py  # 模拟环境（Protocol 实现 + 批量运行）
│   ├── iteration/  (2 files, 364 lines)  # Layer 2: 迭代层（评估→分析→改进→对比闭环）
│   │   ├── __init__.py
│   │   └── engine.py  # 迭代引擎（闭环流程控制）
│   ├── network/  (2 files, 359 lines)  # Layer 2: 网络层（增强特征提取 + GNN/Transformer）
│   │   ├── __init__.py
│   │   └── feature_v2.py  # 增强特征提取（v2 版本）
│   ├── rl/  (4 files, 566 lines)  # Layer 2: 强化学习层（Gym 环境 + 自博弈 + 课程学习）
│   │   ├── __init__.py
│   │   ├── curriculum.py  # 课程学习调度器（难度递增）
│   │   ├── environment.py  # Gym 风格环境（SpideretteEnv）
│   │   └── self_play.py  # 自博弈数据收集器
│   ├── search/  (4 files, 725 lines)  # Layer 2: 搜索层（IS-MCTS / PUCT / 确定化采样）
│   │   ├── __init__.py
│   │   ├── determinization.py  # 确定化采样（暗牌 → 完美信息状态）
│   │   ├── is_mcts.py  # 信息集 MCTS（不完美信息搜索）
│   │   └── puct.py  # PUCT 搜索（AlphaZero 风格）
│   ├── strategy/  (6 files, 1,348 lines)  # Layer 2: 策略层（Protocol + 注册中心 + 组合器）
│   │   ├── __init__.py
│   │   ├── compose.py  # 策略组合器（缓存/并行/超时/投票）
│   │   ├── heuristics.py  # 启发式评估（8 维因子 + 贪心选择）
│   │   ├── mcts.py  # MCTS 策略（UCB1 + 模拟 + 回溯）
│   │   ├── neural.py  # 神经网络策略（MLP 评估 + 推理）
│   │   └── registry.py  # 策略注册中心（Protocol + 装饰器注册）
│   ├── ui/  (3 files, 1,192 lines)  # Layer 3: 展示层（Flask API + Web 前端）
│   │   ├── routes/  (6 files, 849 lines)
│   │   │   ├── __init__.py
│   │   │   ├── analysis.py
│   │   │   ├── export.py
│   │   │   ├── game.py
│   │   │   ├── iteration.py
│   │   │   └── system.py
│   │   ├── static/  (1 files)
│   │   │   └── index.html
│   │   ├── __init__.py
│   │   ├── server.py  # Flask 应用（API 路由注册）
│   │   └── window.py  # 桌面窗口管理（webview）
│   ├── utils/  (4 files, 566 lines)  # Utils: 通用工具（路径 + 配置 + 日志）
│   │   ├── __init__.py
│   │   ├── config.py  # 配置管理（三级优先级：CLI > config.toml > 默认值）
│   │   ├── logging.py  # 日志系统（4 文件分类 + TRACE 级别 + 轮转）
│   │   └── paths.py  # 路径管理（spiderette_data/ 统一存储）
│   └── __init__.py
├── tests/  (19 files, 2,867 lines)  # 单元测试
│   ├── __init__.py
│   ├── conftest.py  # pytest 公共 fixtures（GameState/RuleEngine 工厂）
│   ├── test_analysis.py  # 分析模块测试（指标/对比/导出）
│   ├── test_analysis_extended.py  # 分析扩展测试（遗传/锦标赛/场景）
│   ├── test_compose.py  # 策略组合器测试（缓存/并行/超时）
│   ├── test_generator.py  # 牌局生成器测试（种子/难度）
│   ├── test_heuristics.py  # 启发式评估测试（8 维因子）
│   ├── test_iteration.py  # 迭代引擎测试（闭环流程）
│   ├── test_mcts.py  # MCTS 策略测试（搜索/剪枝/收敛）
│   ├── test_neural.py  # 神经网络策略测试（训练/推理）
│   ├── test_registry.py  # 策略注册中心测试（注册/发现/清单）
│   ├── test_rl.py  # 强化学习测试（环境/自博弈/课程）
│   ├── test_rules.py  # 规则引擎测试（合法移动/终局）
│   ├── test_search.py  # 搜索算法测试（IS-MCTS/PUCT）
│   ├── test_server.py  # Flask API 测试（端点/响应）
│   ├── test_session.py  # 游戏会话测试（状态机/回调）
│   ├── test_simulator.py  # 模拟环境测试（Protocol 实现）
│   ├── test_sync_docs.py  # 文档同步工具测试
│   └── test_types.py  # 不可变类型测试（哈希/序列化）
├── tools/  (4 files, 1,220 lines)  # 开发工具（文档同步、模板生成等）
│   ├── gen_template.py  # 策略模板生成器（快速创建新策略骨架）
│   ├── post_improve.py  # 代码改进后处理（测试 → 同步 → 提交）
│   ├── readme_template.md  # README 模板（sync_docs.py 使用）
│   └── sync_docs.py  # 文档自动同步（扫描源码 → 更新所有文档）
├── build.bat  # Windows 打包脚本（PyInstaller）
├── config.toml  # 项目配置文件（服务器/日志/策略参数）
├── LICENSE  # MIT 许可证
├── main.py  # 程序入口（GUI/CLI/基准测试/实验）
├── Makefile  # 开发命令快捷方式（lint/test/build）
├── pyproject.toml  # 项目元数据与依赖声明（唯一来源）
├── README.md  # 项目说明（本文件）
├── spiderette.spec  # PyInstaller 打包配置
├── 更新日志.md  # 版本变更记录
├── 法律声明.md  # 法律声明与免责条款
├── 算法研究方向.md  # 算法研究路线图
├── 自动生成于  # 自动生成时间戳（sync_docs.py 写入）
└── 项目开发规范.md  # 开发规范与约定（v4.0.0）
```

> 此文件由 `tools/sync_docs.py` 自动生成，是项目结构的唯一权威源。
> 其他文档（README、开发规范等）应引用此处，而非各自维护副本。
