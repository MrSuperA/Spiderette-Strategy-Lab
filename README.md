# Spiderette Strategy Lab — 蜘蛛纸牌移牌策略研究平台

> **v5.0.1** — 38 模块 · 9 策略 · 33 API · 268 测试
>
> 自动生成于 2026-05-04 03:33:50（运行 `python tools/sync_docs.py` 更新）

## 简介

Spiderette Strategy Lab 是一个专注于**蜘蛛纸牌（Spiderette）移牌策略研究**的平台，通过系统化的模拟实验和量化分析，探索并对比不同策略在多难度下的表现。

### 核心特性

- 🎮 **内置模拟器** — 种子可控、可复现的牌局生成和游戏模拟
- 🧠 **9 种策略** — 从贪心基线到信息集 MCTS 到 AlphaZero 风格 PUCT
- 🔍 **信息集搜索** — 正确处理暗牌的不完美信息博弈
- 🤖 **AlphaZero 风格** — PUCT 搜索 + 神经网络先验 + 自博弈训练
- 📊 **量化分析** — 8 维决策因子、策略对比矩阵、弱点自动检测
- 🔄 **策略迭代** — 评估→分析→改进→对比的完整闭环
- 📦 **一键打包** — PyInstaller 独立 .exe（~60MB）

## 快速开始

```bash
# 安装依赖
pip install -e "."

# GUI 模式（推荐）
python main.py

# CLI 模式
python main.py --cli --strategy mcts --seed 42

# 基准测试
python main.py --benchmark greedy mcts is_mcts puct --bench-games 50

# 同步文档（从源码自动生成 README、更新日志等）
python tools/sync_docs.py
```

## 策略列表

| 策略名 | 显示名 | 描述 |
|--------|--------|------|
| `mcts` | MCTS | 蒙特卡洛树搜索，200次迭代 |
| `mcts_fast` | MCTS 快速 | 低迭代次数，适合批量 |
| `mcts_deep` | MCTS 深度 | 高迭代次数，高质量 |
| `greedy` | 贪心 | 启发式评分选择最优移动 |
| `random` | 随机 | 随机选择合法移动（基线） |
| `neural` | 神经网络 | MLP 评估策略（需先训练模型） |
| `is_mcts` | 信息集MCTS | 处理暗牌不完美信息的MCTS |
| `puct` | PUCT搜索 | AlphaZero风格PUCT搜索，支持神经网络先验 |
| `name` | display_name | description |

## 架构

```
src/
├── analysis       # 分析层（指标、对比、导出、遗传、调优）
├── core           # 核心层（类型、规则、会话、信息集、异常）
├── envs           # 环境层（牌局生成器、模拟器）
├── iteration      # 迭代层（策略清单、迭代引擎、改进闭环）
├── network        # 网络层（增强特征提取 v2）
├── rl             # RL 层（环境包装器、自博弈、课程学习）
├── search         # 搜索层（IS-MCTS、PUCT、确定化采样）
├── strategy       # 策略层（MCTS、启发式、神经网络、注册中心）
├── ui             # UI 层（Flask API、pywebview、前端）
├── utils          # utils
```

**代码统计**: 9497 行 · 95 类 · 79 函数

## 平台要求

- Windows 10/11
- Python 3.10+（推荐 3.12）

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 同步文档
python tools/sync_docs.py

# 构建可执行文件
build.bat
```

## 文档

> 以下文档均由 `python tools/sync_docs.py` 自动生成

- [策略列表](docs/strategies.md)
- [API 端点](docs/api.md)
- [模块地图](docs/modules.md)
- [项目开发规范](项目开发规范.md)
- [算法研究方向](算法研究方向.md)
- [更新日志](更新日志.md)

## 许可证

本项目采用 [MIT 许可证](LICENSE) 开源。

## 法律声明

> 完整版见 [法律声明.md](法律声明.md)

**项目性质**：Spiderette Strategy Lab 是**纯学术研究平台**，用于蜘蛛纸牌移牌策略的量化分析与算法探索。本项目不是商业游戏产品，不是赌博工具，不涉及真实货币交易，不提供在线对战功能。

**游戏规则**：蜘蛛纸牌（Spiderette）是经典单人纸牌游戏变体，其规则属于通用公共领域，不受任何单一实体的版权或专利保护。本平台基于公开规则自行实现游戏引擎，未对任何商业游戏产品进行逆向工程。

**AI 与机器学习**：本平台包含的机器学习算法（神经网络、遗传算法、蒙特卡洛树搜索等）仅用于学术研究目的，不保证在任何特定场景下的效果，不对算法决策的正确性或最优性做任何保证。

**随机数**：本平台使用 Python 标准库的伪随机数生成器（`random.Random`），不适用于密码学或安全相关场景。

**免责声明**：在法律允许的最大范围内，本软件按"现状"提供，不附带任何形式的明示或暗示担保。作者和贡献者不对任何直接、间接、偶然、特殊、惩罚性或后果性损害负责。使用本软件产生的任何后果由使用者自行承担。
