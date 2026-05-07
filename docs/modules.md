| 路径 | 说明 | 行数 | 类 | 函数 |
|------|------|------|----|------|
| `src/__init__.py` | Spiderette Strategy Lab — 蜘蛛纸牌移牌策略研究平台 | 21 | 0 | 1 |
| `src/analysis/__init__.py` |  | 1 | 0 | 0 |
| `src/analysis/batch.py` | 批量模拟 — 多进程并行执行 | 63 | 0 | 2 |
| `src/analysis/compare.py` | 多策略并行对比 — 同 seed 多策略运行，实时对比决策差异 | 228 | 4 | 1 |
| `src/analysis/exporter.py` | 牌局导出模块 — 完整牌局记录 + 量化策略分析 | 362 | 3 | 0 |
| `src/analysis/factor.py` | 因子分析器 — 从响应矩阵中发现策略因子 | 267 | 3 | 0 |
| `src/analysis/genetic.py` | 遗传算法优化器 — 自动进化最优策略参数 | 210 | 3 | 0 |
| `src/analysis/metrics.py` | 量化分析引擎 — 胜率、分布、效率、置信区间、多策略对比 | 391 | 3 | 4 |
| `src/analysis/pattern.py` | 模式挖掘 — 从历史数据中发现致胜模式和死局前兆 | 183 | 3 | 0 |
| `src/analysis/profile.py` | 策略量化数据模板 — 描述策略本身的特征，而非牌局结果 | 457 | 8 | 0 |
| `src/analysis/report.py` | 报告生成器 — CSV / JSON / Markdown / 文本摘要 | 178 | 1 | 0 |
| `src/analysis/runner.py` | 实验运行器 — 配置驱动、结果可复现 | 373 | 3 | 0 |
| `src/analysis/scenario.py` | 标准化场景库 + 决策采集器 | 414 | 4 | 0 |
| `src/analysis/tournament.py` | 策略对抗 — 锦标赛模式：同 seed 多策略对比，生成胜率矩阵 | 135 | 3 | 0 |
| `src/analysis/tuning.py` | 策略参数自动调优 — 网格搜索 + 贝叶斯优化 | 258 | 4 | 0 |
| `src/analysis/utils.py` | 分析层公共工具函数 — 消除模块间重复代码 | 108 | 0 | 4 |
| `src/analysis/weakness.py` | 策略弱点自动检测 — 基于量化因子识别策略短板 | 224 | 2 | 2 |
| `src/core/__init__.py` |  | 1 | 0 | 0 |
| `src/core/exceptions.py` | 统一异常体系 — 所有自定义异常的根 | 25 | 5 | 0 |
| `src/core/info_set.py` | 信息集抽象 — 将不完美信息博弈的状态分为可观测和隐藏两部分 | 111 | 3 | 2 |
| `src/core/manifest.py` | 策略清单与迭代记录 — 纯数据层，无业务依赖 | 209 | 3 | 0 |
| `src/core/rules.py` | 规则引擎 — 纯函数集合，无状态无副作用 | 212 | 1 | 0 |
| `src/core/session.py` | GameSession — 可迭代的游戏循环 | 235 | 3 | 0 |
| `src/core/types.py` | 核心类型定义 — 数据模型 + 协议接口 | 322 | 12 | 0 |
| `src/envs/__init__.py` |  | 1 | 0 | 0 |
| `src/envs/generator.py` | 随机牌局生成器 | 104 | 0 | 3 |
| `src/envs/plugins/__init__.py` |  | 1 | 0 | 0 |
| `src/envs/simulator.py` | 模拟器环境 — 内置纯模拟，满足 Environment 协议 | 74 | 1 | 1 |
| `src/iteration/__init__.py` | 策略迭代模块 — 评估→分析→改进→对比的完整闭环 | 17 | 0 | 0 |
| `src/iteration/engine.py` | 策略迭代引擎 — 连接评估→分析→改进→对比的完整闭环 | 349 | 1 | 0 |
| `src/network/__init__.py` | 网络模块 — 增强特征提取、GNN、Transformer | 4 | 0 | 0 |
| `src/network/feature_v2.py` | 增强特征提取 v2 — 200+ 维，捕捉列间关系、红黑交替、历史信息 | 357 | 0 | 4 |
| `src/rl/__init__.py` | 强化学习模块 — Gym 风格环境、奖励函数、PPO 训练器、课程学习 | 18 | 0 | 0 |
| `src/rl/curriculum.py` | 课程学习调度器 — 根据策略表现自适应调整训练难度 | 157 | 2 | 0 |
| `src/rl/environment.py` | Gym 风格的 RL 环境包装器 — 将 GameSession 包装为标准 RL 接口 | 202 | 2 | 0 |
| `src/rl/self_play.py` | 自博弈数据收集器 — 用 MCTS 搜索生成训练数据 | 193 | 3 | 0 |
| `src/search/__init__.py` | 搜索模块 — 前沿搜索算法实现 | 5 | 0 | 0 |
| `src/search/determinization.py` | 暗牌确定化采样器 — 将不完美信息状态转换为多个确定化状态 | 218 | 0 | 7 |
| `src/search/is_mcts.py` | 信息集 MCTS (IS-MCTS) — 处理不完美信息的蒙特卡洛树搜索 | 166 | 1 | 1 |
| `src/search/puct.py` | PUCT 搜索 — AlphaZero 风格的 MCTS，集成神经网络先验 | 340 | 4 | 1 |
| `src/strategy/__init__.py` |  | 1 | 0 | 0 |
| `src/strategy/compose.py` | 策略组合器 — 装饰器模式，替代继承树 | 192 | 1 | 10 |
| `src/strategy/heuristics.py` | 启发式评估函数集 — MCTS 的模拟与评估引导 | 258 | 1 | 9 |
| `src/strategy/mcts.py` | MCTS 策略 — 蒙特卡洛树搜索核心算法 | 424 | 3 | 3 |
| `src/strategy/neural.py` | 神经网络评估策略 — 使用 MLP 评估棋盘状态 | 311 | 3 | 1 |
| `src/strategy/registry.py` | 策略注册中心 — 单一注册点，消除 4 处重复 | 168 | 1 | 15 |
| `src/ui/__init__.py` |  | 1 | 0 | 0 |
| `src/ui/routes/__init__.py` | 路由模块 — Flask Blueprint 拆分 | 10 | 0 | 0 |
| `src/ui/routes/analysis.py` | analysis routes - extracted from server.py | 315 | 0 | 1 |
| `src/ui/routes/export.py` | export routes - extracted from server.py | 118 | 0 | 1 |
| `src/ui/routes/game.py` | game routes - extracted from server.py | 143 | 0 | 1 |
| `src/ui/routes/iteration.py` | iteration routes - extracted from server.py | 114 | 0 | 1 |
| `src/ui/routes/system.py` | system routes - extracted from server.py | 165 | 0 | 1 |
| `src/ui/server.py` | Flask Web 服务 — 研究模式 + 实时可视化 | 238 | 1 | 0 |
| `src/ui/window.py` | Native window wrapper - pywebview + WebView2 + Waitress production server | 146 | 0 | 2 |
| `src/utils/__init__.py` | 工具模块 — 路径解析、通用工具 | 2 | 0 | 0 |
| `src/utils/config.py` | Configuration management for Spiderette Strategy Lab. | 179 | 2 | 6 |
| `src/utils/logging.py` | 统一日志系统 - 分类输出 + 统一管理 | 295 | 1 | 8 |
| `src/utils/paths.py` | 路径解析工具 — 统一处理开发环境和 PyInstaller 打包环境的路径 | 94 | 0 | 8 |