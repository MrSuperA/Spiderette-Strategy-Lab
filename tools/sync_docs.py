"""
文档自动同步工具 — 扫描源码元数据，自动更新所有文档文件
设计原则：单一信息源（代码），文档从代码生成

自动更新的文件：
  - docs/meta.json        — 项目元数据
  - docs/strategies.md    — 策略列表
  - docs/api.md           — API 端点列表
  - docs/modules.md       — 模块地图
  - README.md             — 项目说明（策略表、统计、架构自动更新）
  - 更新日志.md            — 自动追加变更条目

用法：
    python tools/sync_docs.py          # 同步所有文档
    python tools/sync_docs.py --check  # 检查是否有差异（CI 模式）
"""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"


# ═══════════════════════════════════════════════════════════
#  源码扫描
# ═══════════════════════════════════════════════════════════

def scan_strategy_registry() -> list[dict]:
    """扫描策略注册中心，提取所有已注册策略"""
    registry_file = SRC_DIR / "strategy" / "registry.py"
    strategies = []

    content = registry_file.read_text(encoding="utf-8")
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("_register("):
            try:
                parts = line[len("_register("):-1].split(", ", 3)
                if len(parts) >= 3:
                    name = parts[0].strip('"').strip("'")
                    display = parts[1].strip('"').strip("'")
                    desc = parts[3].strip('"').strip("'") if len(parts) > 3 else ""
                    strategies.append({
                        "name": name,
                        "display_name": display,
                        "description": desc,
                    })
            except Exception:
                continue
    return strategies


def scan_modules() -> list[dict]:
    """扫描所有源码模块，提取元数据"""
    modules = []
    for py_file in SRC_DIR.rglob("*.py"):
        if py_file.name == "__init__.py" or "__pycache__" in str(py_file):
            continue

        rel_path = py_file.relative_to(PROJECT_ROOT)
        content = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
            docstring = ast.get_docstring(tree) or ""
        except SyntaxError:
            docstring = ""

        modules.append({
            "path": str(rel_path).replace("\\", "/"),
            "docstring": docstring.split("\n")[0] if docstring else "",
            "lines": len(content.split("\n")),
            "classes": content.count("\nclass "),
            "functions": content.count("\ndef "),
        })
    return sorted(modules, key=lambda m: m["path"])


def scan_api_endpoints() -> list[dict]:
    """扫描 server.py 中的 API 端点"""
    server_file = SRC_DIR / "ui" / "server.py"
    if not server_file.exists():
        return []
    content = server_file.read_text(encoding="utf-8")
    endpoints = []
    pattern = re.compile(r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]+)\])?\)')
    for match in pattern.finditer(content):
        path = match.group(1)
        methods = match.group(2)
        if methods:
            methods = [m.strip().strip('"').strip("'") for m in methods.split(",")]
        else:
            methods = ["GET"]
        endpoints.append({"path": path, "methods": methods})
    return endpoints


def scan_test_count() -> int:
    """扫描测试用例数量"""
    test_dir = PROJECT_ROOT / "tests"
    if not test_dir.exists():
        return 0
    count = 0
    for py_file in test_dir.glob("test_*.py"):
        content = py_file.read_text(encoding="utf-8")
        count += len(re.findall(r"def test_\w+", content))
    return count


def scan_directory_structure() -> list[str]:
    """扫描 src/ 一级子目录"""
    dirs = []
    for d in sorted(SRC_DIR.iterdir()):
        if d.is_dir() and d.name != "__pycache__" and not d.name.startswith("."):
            dirs.append(d.name)
    return dirs


def build_meta(modules, strategies, endpoints, test_count) -> dict:
    """构建元数据"""
    return {
        "synced_at": datetime.now().isoformat(),
        "version": _read_version(),
        "modules": modules,
        "strategies": strategies,
        "endpoints": endpoints,
        "test_count": test_count,
        "stats": {
            "total_modules": len(modules),
            "total_strategies": len(strategies),
            "total_endpoints": len(endpoints),
            "total_lines": sum(m["lines"] for m in modules),
            "total_classes": sum(m["classes"] for m in modules),
            "total_functions": sum(m["functions"] for m in modules),
        },
    }


# ═══════════════════════════════════════════════════════════
#  差异检测（用于更新日志）
# ═══════════════════════════════════════════════════════════

def detect_changes(old_meta: dict, new_meta: dict) -> dict:
    """检测两次同步之间的变化"""
    changes = {
        "new_modules": [],
        "removed_modules": [],
        "new_strategies": [],
        "removed_strategies": [],
        "new_endpoints": [],
        "removed_endpoints": [],
        "test_count_change": 0,
        "line_count_change": 0,
    }

    old_paths = {m["path"] for m in old_meta.get("modules", [])}
    new_paths = {m["path"] for m in new_meta.get("modules", [])}
    changes["new_modules"] = sorted(new_paths - old_paths)
    changes["removed_modules"] = sorted(old_paths - new_paths)

    old_strats = {s["name"] for s in old_meta.get("strategies", [])}
    new_strats = {s["name"] for s in new_meta.get("strategies", [])}
    changes["new_strategies"] = sorted(new_strats - old_strats)
    changes["removed_strategies"] = sorted(old_strats - new_strats)

    old_eps = {e["path"] for e in old_meta.get("endpoints", [])}
    new_eps = {e["path"] for e in new_meta.get("endpoints", [])}
    changes["new_endpoints"] = sorted(new_eps - old_eps)
    changes["removed_endpoints"] = sorted(old_eps - new_eps)

    changes["test_count_change"] = (
        new_meta.get("test_count", 0) - old_meta.get("test_count", 0)
    )
    changes["line_count_change"] = (
        new_meta.get("stats", {}).get("total_lines", 0)
        - old_meta.get("stats", {}).get("total_lines", 0)
    )

    return changes


def has_changes(changes: dict) -> bool:
    """判断是否有实质性变化"""
    return bool(
        changes["new_modules"]
        or changes["removed_modules"]
        or changes["new_strategies"]
        or changes["removed_strategies"]
        or changes["new_endpoints"]
        or changes["removed_endpoints"]
        or changes["test_count_change"] != 0
    )


def generate_changelog_entry(version: str, changes: dict, stats: dict) -> str:
    """生成更新日志条目"""
    lines = [f"## v{version} ({datetime.now():%Y-%m-%d}) — 自动同步\n"]

    if changes["new_modules"]:
        lines.append("### 新增模块")
        for path in changes["new_modules"]:
            lines.append(f"- `{path}`")
        lines.append("")

    if changes["removed_modules"]:
        lines.append("### 移除模块")
        for path in changes["removed_modules"]:
            lines.append(f"- `{path}`")
        lines.append("")

    if changes["new_strategies"]:
        lines.append("### 新增策略")
        for name in changes["new_strategies"]:
            lines.append(f"- `{name}`")
        lines.append("")

    if changes["new_endpoints"]:
        lines.append("### 新增 API 端点")
        for ep in changes["new_endpoints"]:
            lines.append(f"- `{ep}`")
        lines.append("")

    if changes["test_count_change"] != 0:
        sign = "+" if changes["test_count_change"] > 0 else ""
        lines.append(f"### 测试")
        lines.append(f"- 测试用例数变化: {sign}{changes['test_count_change']}")
        lines.append("")

    lines.append("### 项目统计")
    lines.append(f"- 模块数: {stats['total_modules']}")
    lines.append(f"- 策略数: {stats['total_strategies']}")
    lines.append(f"- API 端点: {stats['total_endpoints']}")
    lines.append(f"- 代码行数: {stats['total_lines']}")
    lines.append(f"- 测试用例: {stats.get('test_count', 'N/A')}")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  文档生成
# ═══════════════════════════════════════════════════════════

def generate_strategy_table(strategies: list[dict]) -> str:
    """生成策略列表 Markdown 表格"""
    lines = []
    lines.append("| 策略名 | 显示名 | 描述 |")
    lines.append("|--------|--------|------|")
    for s in strategies:
        lines.append(f"| `{s['name']}` | {s['display_name']} | {s['description']} |")
    return "\n".join(lines)


def generate_api_table(endpoints: list[dict]) -> str:
    """生成 API 端点列表 Markdown 表格"""
    lines = []
    lines.append("| 路径 | 方法 |")
    lines.append("|------|------|")
    for e in endpoints:
        methods = ", ".join(e["methods"])
        lines.append(f"| `{e['path']}` | {methods} |")
    return "\n".join(lines)


def generate_module_map(modules: list[dict]) -> str:
    """生成模块地图 Markdown"""
    lines = []
    current_dir = ""
    for m in modules:
        parts = m["path"].split("/")
        dir_name = "/".join(parts[:-1])
        if dir_name != current_dir:
            current_dir = dir_name
            lines.append(f"\n### `{dir_name}/`\n")
            lines.append("| 文件 | 说明 | 行数 | 类 | 函数 |")
            lines.append("|------|------|------|----|------|")
        desc = m["docstring"][:50] + "…" if len(m["docstring"]) > 50 else m["docstring"]
        lines.append(f"| `{parts[-1]}` | {desc} | {m['lines']} | {m['classes']} | {m['functions']} |")
    return "\n".join(lines)


def generate_readme(stats: dict, strategies: list[dict], modules: list[dict]) -> str:
    """生成完整 README.md"""
    version = _get_changelog_latest_version()
    src_dirs = scan_directory_structure()

    # 策略表
    strat_table = generate_strategy_table(strategies)

    # 架构图
    arch_lines = []
    dir_labels = {
        "core": "核心层（类型、规则、会话、信息集、异常）",
        "envs": "环境层（牌局生成器、模拟器）",
        "strategy": "策略层（MCTS、启发式、神经网络、注册中心）",
        "search": "搜索层（IS-MCTS、PUCT、确定化采样）",
        "network": "网络层（增强特征提取 v2）",
        "rl": "RL 层（环境包装器、自博弈、课程学习）",
        "iteration": "迭代层（策略清单、迭代引擎、改进闭环）",
        "analysis": "分析层（指标、对比、导出、遗传、调优）",
        "ui": "UI 层（Flask API、pywebview、前端）",
    }
    for d in src_dirs:
        label = dir_labels.get(d, d)
        arch_lines.append(f"├── {d:<14} # {label}")
    arch_str = "\n".join(arch_lines)

    # 每层模块数
    layer_stats = {}
    for m in modules:
        parts = m["path"].split("/")
        if len(parts) >= 2 and parts[0] == "src":
            layer = parts[1]
            layer_stats[layer] = layer_stats.get(layer, 0) + 1

    return f"""# Spiderette Strategy Lab — 蜘蛛纸牌移牌策略研究平台

> **v{version}** — {stats['total_modules']} 模块 · {stats['total_strategies']} 策略 · {stats['total_endpoints']} API · {stats.get('test_count', 'N/A')} 测试
>
> 自动生成于 {datetime.now():%Y-%m-%d %H:%M:%S}（运行 `python tools/sync_docs.py` 更新）

## 简介

Spiderette Strategy Lab 是一个专注于**蜘蛛纸牌（Spiderette）移牌策略研究**的平台，通过系统化的模拟实验和量化分析，探索并对比不同策略在多难度下的表现。

### 核心特性

- 🎮 **内置模拟器** — 种子可控、可复现的牌局生成和游戏模拟
- 🧠 **{stats['total_strategies']} 种策略** — 从贪心基线到信息集 MCTS 到 AlphaZero 风格 PUCT
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

{strat_table}

## 架构

```
src/
{arch_str}
```

**代码统计**: {stats['total_lines']} 行 · {stats['total_classes']} 类 · {stats['total_functions']} 函数

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
"""


# ═══════════════════════════════════════════════════════════
#  主同步流程
# ═══════════════════════════════════════════════════════════

def sync_all(check_only: bool = False) -> bool:
    """同步所有文档"""
    print(f"[sync_docs] 扫描源码...")
    modules = scan_modules()
    strategies = scan_strategy_registry()
    endpoints = scan_api_endpoints()
    test_count = scan_test_count()
    stats_data = build_meta(modules, strategies, endpoints, test_count)
    stats = stats_data["stats"]
    stats["test_count"] = test_count

    print(f"[sync_docs] 发现 {stats['total_modules']} 模块, "
          f"{stats['total_strategies']} 策略, "
          f"{stats['total_endpoints']} 端点, "
          f"{test_count} 测试, "
          f"{stats['total_lines']} 行代码")

    meta_file = PROJECT_ROOT / "docs" / "meta.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)

    # 加载旧元数据用于差异检测
    old_meta = {}
    if meta_file.exists():
        try:
            old_meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    changes = detect_changes(old_meta, stats_data)

    if check_only:
        if has_changes(changes):
            print("[sync_docs] ❌ 文档需要更新")
            print(f"  变化: {json.dumps({k: v for k, v in changes.items() if v}, ensure_ascii=False)}")
            return False
        else:
            print("[sync_docs] ✅ 文档已是最新")
            return True

    # ── 写入 meta.json ──
    meta_file.write_text(json.dumps(stats_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[sync_docs] 已更新 docs/meta.json")

    # ── 生成 docs/strategies.md ──
    strategies_doc = PROJECT_ROOT / "docs" / "strategies.md"
    content = f"# 策略列表\n\n> 自动生成于 {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
    content += generate_strategy_table(strategies)
    strategies_doc.write_text(content, encoding="utf-8")
    print(f"[sync_docs] 已更新 docs/strategies.md")

    # ── 生成 docs/api.md ──
    api_doc = PROJECT_ROOT / "docs" / "api.md"
    content = f"# API 端点\n\n> 自动生成于 {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
    content += generate_api_table(endpoints)
    api_doc.write_text(content, encoding="utf-8")
    print(f"[sync_docs] 已更新 docs/api.md")

    # ── 生成 docs/modules.md ──
    modules_doc = PROJECT_ROOT / "docs" / "modules.md"
    content = f"# 模块地图\n\n> 自动生成于 {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
    content += f"**总计**: {stats['total_lines']} 行代码, "
    content += f"{stats['total_classes']} 个类, "
    content += f"{stats['total_functions']} 个函数\n\n"
    content += generate_module_map(modules)
    modules_doc.write_text(content, encoding="utf-8")
    print(f"[sync_docs] 已更新 docs/modules.md")

    # ── 生成 README.md ──
    readme = PROJECT_ROOT / "README.md"
    readme.write_text(generate_readme(stats, strategies, modules), encoding="utf-8")
    print(f"[sync_docs] 已更新 README.md")

    # ── 追加更新日志 ──
    if has_changes(changes):
        latest = _get_changelog_latest_version()
        next_ver = _next_version(latest)
        entry = generate_changelog_entry(next_ver, changes, stats)
        changelog = PROJECT_ROOT / "更新日志.md"
        if changelog.exists():
            existing = changelog.read_text(encoding="utf-8")
            # 在第一个 ## 之前插入新条目
            first_heading = existing.find("\n## ")
            if first_heading > 0:
                new_content = existing[:first_heading] + "\n" + entry + existing[first_heading:]
            else:
                new_content = existing + "\n" + entry
        else:
            new_content = "# 更新日志\n\n" + entry
        changelog.write_text(new_content, encoding="utf-8")
        print(f"[sync_docs] 已追加更新日志条目")
    else:
        print(f"[sync_docs] 无实质性变化，跳过更新日志")

    print(f"[sync_docs] ✅ 同步完成")
    return True


def _read_version() -> str:
    """读取版本号（优先从 pyproject.toml）"""
    try:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib
        with open(pyproject, "rb") as f:
            return tomllib.load(f).get("project", {}).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _next_version(current: str) -> str:
    """递增补丁版本号"""
    parts = current.split(".")
    if len(parts) >= 3:
        parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts)


def _get_changelog_latest_version() -> str:
    """从更新日志中提取最新版本号"""
    changelog = PROJECT_ROOT / "更新日志.md"
    if not changelog.exists():
        return _read_version()
    content = changelog.read_text(encoding="utf-8")
    import re
    match = re.search(r"^## v(\d+\.\d+\.\d+)", content, re.MULTILINE)
    if match:
        return match.group(1)
    return _read_version()


if __name__ == "__main__":
    check = "--check" in sys.argv
    success = sync_all(check_only=check)
    sys.exit(0 if success else 1)
