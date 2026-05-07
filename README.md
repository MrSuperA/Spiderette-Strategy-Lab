# Spiderette Strategy Lab

> **v5.0.5** — 蜘蛛纸牌移牌策略研究平台
>
> 0 模块 · 0 策略 · 0 API · 321 测试 · 0 行代码

Spiderette Strategy Lab 是一个专注于**蜘蛛纸牌（Spiderette）移牌策略研究**的量化分析平台。通过系统化的模拟实验和多维度数据分析，探索并对比不同策略在多难度下的表现。

**核心定位**：不是游戏，不是工具，是**策略研究的实验基础设施**。

---

## 目录

- [为什么做这个项目](#为什么做这个项目)
- [与同类项目的区别](#与同类项目的区别)
- [核心设计亮点](#核心设计亮点)
- [快速开始](#快速开始)
- [新手教程](#新手教程)
- [项目结构](#项目结构)
- [策略一览](#策略一览)
- [API 端点](#api-端点)
- [开发指南](#开发指南)
- [常见问题](#常见问题)
- [文档索引](#文档索引)
- [法律声明](#法律声明)
- [许可证](#许可证)

---

## 为什么做这个项目

蜘蛛纸牌是一个经典的**不完美信息博弈**——你不知道暗牌是什么，但必须做出最优决策。这和围棋（完美信息）有本质区别，使得传统 AlphaZero 方法不能直接套用。

本项目的核心问题是：**在信息不完整的情况下，什么样的搜索策略能做出更好的决策？**

我们构建了一个可复现的实验平台，让不同策略在同一组牌局上公平竞争，用数据说话。

---

## 与同类项目的区别

| 维度 | 传统纸牌 AI | 本项目 |
|------|------------|--------|
| **信息模型** | 完美信息（假设暗牌已知） | 不完美信息（正确处理暗牌不确定性） |
| **策略对比** | 单策略展示 | 多策略同 seed 公平对比 |
| **评估体系** | 胜率单一指标 | 8 维决策因子 + 置信区间 + 弱点检测 |
| **搜索算法** | 标准 MCTS | IS-MCTS（信息集）+ PUCT（神经网络先验） |
| **训练方式** | 无 / 手工调参 | 自博弈 + 课程学习 + 遗传算法自动调优 |
| **可复现性** | 依赖随机种子 | 种子锁定 + 哈希追踪 + 版本化清单 |
| **实验管理** | 手动运行 | 配置驱动 + 一键迭代 + 自动文档同步 |
| **扩展方式** | 改代码 | Protocol 接口 + 注册中心 + 策略组合器 |

---

## 核心设计亮点

### 1. 不完美信息处理

蜘蛛纸牌的暗牌是核心挑战。本项目实现了三种处理方式：

- **贪心/MCTS**：忽略暗牌，只基于明牌决策（基线）
- **IS-MCTS**：对暗牌进行确定化采样，每个采样状态独立跑 MCTS，跨采样聚合决策
- **PUCT**：AlphaZero 风格，用神经网络先验引导搜索，处理信息不完整

### 2. 不可变状态模型

所有游戏状态（`GameState`）都是 `frozen dataclass`，规则引擎返回新状态而非修改旧状态。这保证了：

- 状态哈希可缓存（MCTS 节点去重）
- 多线程安全（无竞态条件）
- 牌局可回放（每步快照完整）

### 3. 策略即函数

策略通过 `Strategy` Protocol 定义（`name` + `choose`），不依赖继承树。组合器用装饰器模式增强行为（缓存、并行、超时），不改变签名。

```python
class Strategy(Protocol):
    name: str
    def choose(self, state: GameState, legal: Sequence[Move]) -> Optional[Move]: ...
```

### 4. 8 维决策因子分析

每个策略的决策行为被量化为 8 个维度：

| 因子 | 含义 |
|------|------|
| `same_suit` | 同花色优先度 |
| `col_empty` | 空列利用倾向 |
| `col_diversity` | 列多样性偏好 |
| `deal_timing` | 发牌时机判断 |
| `tempo` | 节奏控制（步数效率） |
| `risk` | 风险承受度 |
| `info_value` | 信息价值评估 |
| `chain_length` | 长链构建偏好 |

### 5. 策略迭代闭环

```
评估 → 分析弱点 → 生成改进建议 → 应用改进 → 重新评估 → 对比
```

整个流程可通过 `IterationEngine.iterate()` 一键执行，每次迭代产生可序列化、可比较的完整记录。

### 6. 文档从代码生成

`tools/sync_docs.py` 扫描源码元数据（模块、策略、API、测试数），自动更新 README、策略列表、API 文档、模块地图、更新日志。单一信息源，避免文档与代码脱节。

---

## 快速开始

### 环境要求

- Windows 10/11（macOS/Linux 部分功能可用）
- Python 3.10+（推荐 3.12）

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd Spiderette Strategy Lab

# 安装（开发模式）
pip install -e ".[dev]"
```

### 运行

```bash
# GUI 模式（推荐）— 启动独立窗口
python main.py

# CLI 模式 — 运行一局
python main.py --cli --strategy mcts --seed 42

# 基准测试 — 多策略对比
python main.py --benchmark mcts mcts_fast mcts_deep greedy --bench-games 50

# 实验运行 — 配置驱动
python main.py --experiment experiments/configs/my_experiment.toml
```

---

## 新手教程

### 第一步：跑通一局

```bash
python main.py --cli --strategy mcts --seed 1
```

你会看到类似输出：

```
[Spiderette] seed=1 difficulty=2 strategy=mcts
[Spiderette] 开始运行...
  #  1 0→3 (1张) [2ms] legal=12
  #  2 5→8 (2张) [1ms] legal=11
  ...
[结果] WIN
[统计] 步数=87 耗时=156ms 完成=8/8
```

- `0→3`：从第 0 列移动到第 3 列
- `legal=12`：当前有 12 个合法移动
- `WIN/DEADLOCK/PLAYING`：游戏结果

### 第二步：对比不同策略

```bash
python main.py --benchmark mcts mcts_fast mcts_deep greedy --bench-games 20
```

输出会显示每个策略的胜率、置信区间、平均步数。相同 seed 保证公平对比。

### 第三步：查看策略分析

```bash
# 运行基准测试并导出报告
python main.py --benchmark mcts mcts_fast mcts_deep greedy --bench-games 50 --bench-output experiments/results

# 查看导出的报告
cat experiments/results/benchmark_*.md
```

### 第四步：运行策略迭代

```python
from src.iteration.engine import IterationEngine
from src.strategy.registry import get_strategy

engine = IterationEngine()
strategy = get_strategy("mcts")
record = engine.iterate(strategy, num_games=100)

# 查看迭代结果
print(f"胜率变化: {record.baseline.win_rate:.1%} → {record.improved.win_rate:.1%}")
print(f"弱点: {[w.factor for w in record.weaknesses]}")
print(f"改进建议: {[a.description for a in record.actions]}")
```

### 第五步：自定义策略

```python
from src.strategy.registry import register_strategy
from src.core.types import GameState, Move, Strategy
from typing import Optional, Sequence

class MyStrategy:
    name = "my_strategy"
    
    def choose(self, state: GameState, legal: Sequence[Move]) -> Optional[Move]:
        # 你的决策逻辑
        return legal[0] if legal else None

register_strategy("my_strategy", "我的策略", MyStrategy, "自定义策略示例")
```

---

## 项目结构

```
Spiderette Strategy Lab/
├── .github/                              # GitHub Actions 工作流配置
│   └── workflows/                        # CI/CD 流水线
├── dist/                                 # 构建输出目录
│   ├── spiderette_data/                  # 运行时数据目录
│   │   └── logs/                         # 运行日志目录
│   │       ├── app.log                   # 应用日志
│   │       ├── error.log                 # 错误日志
│   │       ├── strategy.log              # 策略日志
│   │       └── training.log              # 训练日志
│   └── SpideretteStrategyLab_v5.0.5.exe  # 打包输出的可执行文件
├── docs/                                 # 项目文档（自动生成）
│   ├── api.md                            # API 接口文档
│   ├── meta.json                         # 项目元数据
│   ├── modules.md                        # 模块说明文档
│   ├── project_structure.md              # 项目结构文档
│   └── strategies.md                     # 策略说明文档
├── experiments/                          # 实验配置与结果
│   └── configs/                          # 实验配置文件（TOML）
├── iterations/                           # 迭代记录
│   └── .gitkeep                          # 占位文件
├── logs/                                 # 运行日志
├── manifests/                            # 策略清单目录
│   └── custom_mcts_v2.json               # 自定义 MCTS 策略清单
├── models/                               # 训练好的模型文件
│   ├── .gitkeep                          # 占位文件
│   └── neural_model.npz                  # 训练好的神经网络模型
├── src/                                  # 核心源码
│   ├── analysis/                         # 分析工具（指标、对比、报告生成）
│   │   ├── batch.py                      # 批量分析工具
│   │   ├── compare.py                    # 策略对比分析
│   │   ├── exporter.py                   # 分析结果导出
│   │   ├── factor.py                     # 因子分析
│   │   ├── genetic.py                    # 遗传算法优化
│   │   ├── metrics.py                    # 性能指标计算
│   │   ├── pattern.py                    # 牌局模式识别
│   │   ├── profile.py                    # 策略画像生成
│   │   ├── report.py                     # 分析报告生成
│   │   ├── runner.py                     # 分析任务运行器
│   │   ├── scenario.py                   # 场景模拟分析
│   │   ├── tournament.py                 # 锦标赛对战分析
│   │   ├── tuning.py                     # 参数调优工具
│   │   ├── utils.py                      # 分析工具函数
│   │   └── weakness.py                   # 弱点检测分析
│   ├── core/                             # 核心数据结构（GameState, Move, Rules）
│   │   ├── exceptions.py                 # 自定义异常类
│   │   ├── info_set.py                   # 信息集抽象
│   │   ├── manifest.py                   # 策略清单定义
│   │   ├── rules.py                      # 游戏规则实现
│   │   ├── session.py                    # 对局会话管理
│   │   └── types.py                      # 核心类型定义（GameState, Move 等）
│   ├── envs/                             # 环境模拟器（牌局生成）
│   │   ├── plugins/                      # 环境插件目录
│   │   ├── generator.py                  # 牌局生成器
│   │   └── simulator.py                  # 牌局模拟器
│   ├── iteration/                        # 策略迭代引擎
│   │   └── engine.py                     # 策略迭代引擎
│   ├── network/                          # 神经网络模型
│   │   └── feature_v2.py                 # V2 特征提取
│   ├── rl/                               # 强化学习（自博弈、课程学习）
│   │   ├── curriculum.py                 # 课程学习调度
│   │   ├── environment.py                # RL 环境封装
│   │   └── self_play.py                  # 自博弈训练
│   ├── search/                           # 搜索算法（IS-MCTS, PUCT）
│   │   ├── determinization.py            # 信息集确定化采样
│   │   ├── is_mcts.py                    # 信息集 MCTS 实现
│   │   └── puct.py                       # PUCT 搜索算法
│   ├── strategy/                         # 策略实现（贪心、MCTS、神经网络等）
│   │   ├── compose.py                    # 策略组合与切换
│   │   ├── heuristics.py                 # 启发式策略（贪心等）
│   │   ├── mcts.py                       # MCTS 策略实现
│   │   ├── neural.py                     # 神经网络策略
│   │   └── registry.py                   # 策略注册与发现
│   ├── ui/                               # GUI/Web 界面
│   │   ├── routes/                       # Web 路由目录
│   │   │   ├── analysis.py               # 分析页面路由
│   │   │   ├── export.py                 # 导出页面路由
│   │   │   ├── game.py                   # 对局页面路由
│   │   │   ├── iteration.py              # 迭代页面路由
│   │   │   └── system.py                 # 系统页面路由
│   │   ├── static/                       # 静态资源目录
│   │   │   └── index.html                # 前端主页
│   │   ├── server.py                     # Web 服务器
│   │   └── window.py                     # GUI 窗口管理
│   └── utils/                            # 通用工具函数
│       ├── config.py                     # 配置文件读取
│       ├── logging.py                    # 日志配置
│       └── paths.py                      # 路径工具函数
├── tests/                                # 单元测试
│   ├── _gen.py                           # 测试数据生成器
│   ├── _gen_test.py                      # 生成器测试
│   ├── conftest.py                       # pytest 公共 fixtures
│   ├── test_analysis.py                  # 分析模块测试
│   ├── test_analysis_extended.py         # 分析扩展测试
│   ├── test_api_match.py                 # API 对战测试
│   ├── test_compose.py                   # 策略组合测试
│   ├── test_generator.py                 # 生成器测试
│   ├── test_heuristics.py                # 启发式策略测试
│   ├── test_iteration.py                 # 迭代引擎测试
│   ├── test_mcts.py                      # MCTS 测试
│   ├── test_neural.py                    # 神经网络测试
│   ├── test_registry.py                  # 策略注册测试
│   ├── test_rl.py                        # 强化学习测试
│   ├── test_rules.py                     # 规则测试
│   ├── test_search.py                    # 搜索算法测试
│   ├── test_server.py                    # 服务器测试
│   ├── test_session.py                   # 会话测试
│   ├── test_simulator.py                 # 模拟器测试
│   ├── test_sync_docs.py                 # 文档同步测试
│   └── test_types.py                     # 类型测试
├── tools/                                # 开发工具（文档同步、模板生成等）
│   ├── .file_hashes.json                 # 文件哈希缓存（增量同步用）
│   ├── .symbol_snapshots.json            # 符号快照缓存（变更检测用）
│   ├── gen_template.py                   # 模板生成工具
│   ├── post_improve.py                   # 代码改进后处理
│   ├── readme_template.md                # README 模板文件
│   └── sync_docs.py                      # 文档自动同步脚本
├── .gitignore                            # Git 忽略规则
├── .pre-commit-config.yaml               # Pre-commit 钩子配置
├── LICENSE                               # MIT 许可证
├── Makefile                              # 构建自动化脚本
├── README.md                             # 项目说明（本文件）
├── build.bat                             # Windows 打包脚本
├── config.toml                           # 运行时配置文件
├── main.py                               # 程序入口
├── pyproject.toml                        # 项目配置与依赖
├── spiderette.spec                       # PyInstaller 打包配置
├── 更新日志.md                               # 版本更新记录
├── 法律声明.md                               # 法律声明与免责条款
├── 算法研究方向.md                             # 算法研究路线图
└── 项目开发规范.md                             # 开发规范与约定

```

> 目录树由 `tools/sync_docs.py` 自动生成，标注了每个目录的文件数和代码行数。
> 详细的模块说明见 [docs/modules.md](docs/modules.md)。

---

## 策略一览

| 策略名称 | 显示名称 | 描述 |
|----------|----------|------|
| `mcts` | MCTS | 蒙特卡洛树搜索，200次迭代 |
| `mcts_fast` | MCTS 快速 | 低迭代次数，适合批量 |
| `mcts_deep` | MCTS 深度 | 高迭代次数，高质量 |
| `greedy` | 贪心 | 启发式评分选择最优移动 |
| `random` | 随机 | 随机选择合法移动（基线） |
| `neural` | 神经网络 | MLP 评估策略（需先训练模型） |
| `is_mcts` | 信息集MCTS | 处理暗牌不完美信息的MCTS |
| `puct` | PUCT搜索 | AlphaZero风格PUCT搜索，支持神经网络先验 |


## API 端点

> 完整 API 文档见 [docs/api.md](docs/api.md)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主页面 |
| GET | `/api/state` | 当前游戏状态 |
| POST | `/api/move` | 执行移动 |
| POST | `/api/deal` | 发牌 |
| POST | `/api/reset` | 重置游戏 |
| GET | `/api/strategies` | 策略列表 |
| POST | `/api/strategy/set` | 切换策略 |
| GET | `/api/benchmark` | 运行基准测试 |
| GET | `/api/analysis` | 策略分析 |
| GET | `/api/stream` | SSE 事件流 |

> 共 0 个端点，完整列表见 [docs/api.md](docs/api.md)

---

## 开发指南

### 代码规范

- **格式化**：`black --line-length 100`
- **Lint**：`ruff check src/ tests/`
- **类型检查**：`mypy src/`
- **测试**：`pytest tests/ -v`

### 提交规范

```
feat: 新功能
fix: 修复
docs: 文档
style: 格式（不影响逻辑）
refactor: 重构
test: 测试
chore: 构建/工具
```

### 添加新策略

1. 在 `src/strategy/` 下创建新文件
2. 实现 `Strategy` Protocol（`name` + `choose`）
3. 在 `src/strategy/registry.py` 中注册
4. 添加测试 `tests/test_your_strategy.py`
5. 运行 `python tools/sync_docs.py` 更新文档

### 运行测试

```bash
# 全部测试
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=src --cov-report=term-missing

# 特定模块
pytest tests/test_mcts.py -v
```

---

## 常见问题

### Q: 暗牌是怎么处理的？

A: 三种方式：
1. **忽略**（贪心/MCTS）：只看明牌，简单但次优
2. **确定化采样**（IS-MCTS）：随机生成暗牌排列，每个排列独立搜索，跨排列聚合
3. **神经网络先验**（PUCT）：用神经网络预测暗牌概率，引导搜索

### Q: 为什么用 frozen dataclass？

A: 不可变状态保证了：
- 哈希可缓存（MCTS 节点去重）
- 多线程安全（无竞态条件）
- 牌局可回放（每步快照完整）

### Q: 如何复现某个实验？

A: 每个实验都有 seed，相同 seed + 相同策略 = 相同结果。查看 `experiments/results/` 下的 JSON 文件，里面有完整配置。

### Q: 支持自定义策略吗？

A: 支持。实现 `Strategy` Protocol，注册到 `registry.py`，即可参与基准测试和迭代优化。详见 [新手教程 - 第五步](#第五步自定义策略)。

### Q: 如何扩展分析维度？

A: 在 `src/analysis/factor.py` 中添加新的因子计算函数，然后在 `metrics.py` 中调用。8 维因子是默认配置，可按需增减。

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [README.md](README.md) | 项目说明（本文档） |
| [更新日志.md](更新日志.md) | 版本变更记录 |
| [docs/meta.json](docs/meta.json) | 项目元数据（模块、策略、端点统计） |
| [docs/strategies.md](docs/strategies.md) | 策略列表（自动生成） |
| [docs/api.md](docs/api.md) | API 端点列表（自动生成） |
| [docs/modules.md](docs/modules.md) | 模块地图（自动生成） |

---

## 法律声明

本项目是**纯学术研究平台**，不涉及真实货币交易、不提供联网对战功能。蜘蛛纸牌规则属于公共领域，本平台基于公开规则自行实现游戏引擎。

完整法律声明见 [法律声明.md](法律声明.md)。

---

## 许可证

MIT License

Copyright (c) 2026 Spiderette Strategy Lab Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
