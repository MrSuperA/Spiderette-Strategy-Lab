"""
文档自动同步工具 — 扫描源码元数据，自动更新所有文档文件
设计原则：单一信息源（代码），文档从代码生成

核心机制：
  - 文件哈希追踪：SHA256 对比源码内容变化，不只看结构增删
  - AST 差异分析：提取函数/类级别的有意义变更描述
  - 变更日志自动生成：基于实际代码修改生成有意义的条目

自动更新的文件：
  - docs/meta.json        — 项目元数据（含文件哈希）
  - docs/strategies.md    — 策略列表
  - docs/api.md           — API 端点列表
  - docs/modules.md       — 模块地图
  - README.md             — 项目说明（策略表、统计、架构自动更新）
  - 更新日志.md            — 自动追加变更条目

用法：
    python tools/sync_docs.py                          # 同步所有文档
    python tools/sync_docs.py --check                  # 检查是否有差异（CI 模式）
    python tools/sync_docs.py --message "描述"          # 手动指定变更描述
    python tools/sync_docs.py --bump-version major      # 强制版本递增 (major/minor/patch)
    python tools/sync_docs.py --no-changelog            # 跳过更新日志
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── 路径常量 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TOOLS_DIR = PROJECT_ROOT / "tools"
DOCS_DIR = PROJECT_ROOT / "docs"
CHANGELOG_FILE = PROJECT_ROOT / "更新日志.md"
HASHES_FILE = TOOLS_DIR / ".file_hashes.json"
SYMBOLS_FILE = TOOLS_DIR / ".symbol_snapshots.json"

# ── 忽略规则 ──────────────────────────────────────────────────────────────────
_IGNORED_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}
_IGNORED_FILES = {"__init__.py", ".DS_Store"}


# ── 版本管理 ──────────────────────────────────────────────────────────────────
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


def _read_project_meta() -> dict:
    """从 pyproject.toml 读取完整项目元数据（唯一源头）"""
    try:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        project = data.get("project", {})
        return {
            "name": project.get("name", ""),
            "display_name": project.get("display_name", project.get("name", "")),
            "version": project.get("version", "0.0.0"),
            "description": project.get("description", ""),
            "requires_python": project.get("requires-python", ""),
            "license": (project.get("license") or {}).get("text", ""),
        }
    except Exception:
        return {
            "name": "",
            "display_name": "",
            "version": "0.0.0",
            "description": "",
            "requires_python": "",
            "license": "",
        }


def _next_version(current: str) -> str:
    """递增补丁版本号"""
    parts = current.split(".")
    if len(parts) >= 3:
        parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts)


# ── 文件哈希追踪 ──────────────────────────────────────────────────────────────
def _file_sha256(path: Path) -> str:
    """计算文件 SHA256"""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _load_hashes() -> dict[str, str]:
    """加载上次同步时的文件哈希"""
    if HASHES_FILE.exists():
        try:
            return json.loads(HASHES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_hashes(hashes: dict[str, str]) -> None:
    """保存文件哈希"""
    HASHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    HASHES_FILE.write_text(json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8")


def _scan_current_hashes() -> dict[str, str]:
    """扫描当前所有源码文件的哈希"""
    hashes: dict[str, str] = {}
    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        rel = str(py_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
        hashes[rel] = _file_sha256(py_file)
    return hashes


# ── Git 操作 ──────────────────────────────────────────────────────────────────
def _git(args: list[str], cwd: Path | None = None) -> str:
    """执行 git 命令并返回 stdout"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd or PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("git 未安装或不在 PATH 中")


def _git_has_changes() -> bool:
    """检查是否有未提交的变更"""
    status = _git(["status", "--porcelain"])
    return bool(status.strip())


def _git_diff_stat() -> str:
    """获取变更统计摘要"""
    return _git(["diff", "--stat"])


def _git_add_and_commit(message: str, files: list[str]) -> bool:
    """暂存指定文件并提交"""
    try:
        for f in files:
            _git(["add", f])
        _git(["commit", "-m", message])
        return True
    except RuntimeError as e:
        print(f"⚠️  Git 提交失败: {e}")
        return False


# ── AST 符号提取 ──────────────────────────────────────────────────────────────
def _extract_ast_symbols(filepath: Path) -> dict[str, list[str]]:
    """从 Python 文件中提取顶层符号（类名、函数名）"""
    try:
        file_content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(file_content)
        classes: list[str] = []
        functions: list[str] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        return {"classes": classes, "functions": functions}
    except (SyntaxError, OSError):
        return {"classes": [], "functions": []}


def _load_symbol_snapshots() -> dict[str, dict]:
    """从文件加载符号快照"""
    if SYMBOLS_FILE.exists():
        try:
            return json.loads(SYMBOLS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_symbol_snapshots(snapshots: dict[str, dict]) -> None:
    """保存符号快照"""
    SYMBOLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SYMBOLS_FILE.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8")


def _analyze_file_changes(changed_files: list[str]) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """分析变更文件，提取有意义的变更描述"""
    old_snapshots = _load_symbol_snapshots()
    changes: dict[str, list[str]] = {}
    new_snapshots: dict[str, dict] = {}

    for fpath in changed_files:
        full_path = PROJECT_ROOT / fpath
        new_symbols = (
            _extract_ast_symbols(full_path)
            if full_path.exists()
            else {"classes": [], "functions": []}
        )
        new_snapshots[fpath] = new_symbols

        if not full_path.exists():
            changes[fpath] = ["模块已删除"]
            continue

        if fpath not in old_snapshots:
            descs: list[str] = []
            if new_symbols["classes"]:
                descs.append(f"新增类: {', '.join(new_symbols['classes'])}")
            if new_symbols["functions"]:
                descs.append(f"新增函数: {', '.join(new_symbols['functions'])}")
            if not descs:
                descs.append("新增模块")
            changes[fpath] = descs
            continue

        old = old_snapshots[fpath]
        old_classes = set(old.get("classes", []))
        new_classes = set(new_symbols.get("classes", []))
        old_funcs = set(old.get("functions", []))
        new_funcs = set(new_symbols.get("functions", []))

        added_classes = sorted(new_classes - old_classes)
        removed_classes = sorted(old_classes - new_classes)
        added_funcs = sorted(new_funcs - old_funcs)
        removed_funcs = sorted(old_funcs - new_funcs)
        common_funcs = old_funcs & new_funcs

        descs = []
        if added_classes:
            descs.append(f"新增类: {', '.join(added_classes)}")
        if removed_classes:
            descs.append(f"移除类: {', '.join(removed_classes)}")
        if added_funcs:
            descs.append(f"新增函数: {', '.join(added_funcs)}")
        if removed_funcs:
            descs.append(f"移除函数: {', '.join(removed_funcs)}")

        if common_funcs and not added_funcs and not removed_funcs and not added_classes and not removed_classes:
            sorted_common = sorted(common_funcs)
            descs.append(
                f"函数实现修改: {', '.join(sorted_common[:5])}"
                + (" 等" if len(sorted_common) > 5 else "")
            )

        if not descs:
            descs.append("内容修改")

        changes[fpath] = descs

    return changes, new_snapshots


# ── 扫描函数 ──────────────────────────────────────────────────────────────────
def scan_strategy_registry() -> list[dict]:
    """扫描策略注册中心，提取所有已注册策略"""
    registry_file = SRC_DIR / "strategy" / "registry.py"
    strategies: list[dict] = []
    try:
        content = registry_file.read_text(encoding="utf-8")
        for line in content.split("\n"):
            line = line.strip()
            if not line.startswith("_register("):
                continue
            parts = line[len("_register(") : -1].split(", ", 3)
            if len(parts) >= 3:
                if not (parts[0].startswith('"') or parts[0].startswith("'")):
                    continue
                name = parts[0].strip('"').strip("'")
                display = parts[1].strip('"').strip("'")
                desc = (
                    parts[3].strip('"').strip("'")
                    if len(parts) > 3
                    else ""
                )
                strategies.append(
                    {"name": name, "display_name": display, "description": desc}
                )
    except Exception:
        pass
    return strategies


def scan_modules() -> list[dict]:
    """扫描所有源码模块，提取元数据"""
    modules: list[dict] = []
    for py_file in SRC_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        rel_path = py_file.relative_to(PROJECT_ROOT)
        content = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
            docstring = ast.get_docstring(tree) or ""
            modules.append(
                {
                    "path": str(rel_path).replace("\\", "/"),
                    "docstring": docstring.split("\n")[0] if docstring else "",
                    "lines": len(content.split("\n")),
                    "classes": content.count("\nclass "),
                    "functions": content.count("\ndef "),
                }
            )
        except SyntaxError:
            docstring = ""
    return sorted(modules, key=lambda m: m["path"])


def scan_api_endpoints() -> list[dict]:
    """扫描所有路由文件中的 API 端点（server.py + routes/*.py）"""
    endpoints: list[dict] = []
    pattern = re.compile(
        r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]+)\])?\)'
    )
    seen: set[str] = set()

    routes_dir = SRC_DIR / "ui" / "routes"
    if routes_dir.exists():
        for route_file in sorted(routes_dir.glob("*.py")):
            if route_file.name.startswith("_"):
                continue
            content = route_file.read_text(encoding="utf-8")
            for match in pattern.finditer(content):
                path = match.group(1)
                if path in seen:
                    continue
                seen.add(path)
                methods = match.group(2)
                if methods:
                    methods = [m.strip().strip('"').strip("'") for m in methods.split(",")]
                else:
                    methods = ["GET"]
                endpoints.append({"path": path, "methods": methods})

    server_file = SRC_DIR / "ui" / "server.py"
    if server_file.exists():
        content = server_file.read_text(encoding="utf-8")
        for match in pattern.finditer(content):
            path = match.group(1)
            if path in seen:
                continue
            seen.add(path)
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
    dirs: list[str] = []
    for d in sorted(SRC_DIR.iterdir()):
        if not d.is_dir():
            continue
        if d.name != "__pycache__" and not d.name.startswith("."):
            dirs.append(d.name)
    return dirs


def _should_ignore(name: str) -> bool:
    """判断是否应忽略该文件/目录"""
    if name in _IGNORED_DIRS or name in _IGNORED_FILES:
        return True
    if name.endswith((".pyc", ".pyo", ".egg-info")):
        return True
    return False


def scan_full_project_tree() -> str:
    """扫描完整项目目录树，返回带注释的 Markdown 代码块格式树形结构

    改进点：
    - 每个目录显示行数统计（如 "16 files, 2,847 lines"）
    - 关键目录和文件附带中文注释说明用途
    - 过滤临时文件和构建产物
    """
    _COMMENTS = {
        # ── 顶层目录 ──
        "src": "核心源码",
        "tests": "单元测试",
        "tools": "开发工具（文档同步、模板生成等）",
        "docs": "项目文档（自动生成）",
        "experiments": "实验配置与结果",
        "iterations": "迭代记录",
        "models": "训练好的模型文件",
        "logs": "运行日志",
        "dist": "构建输出目录",
        "manifests": "策略清单目录",
        # ── src/ 子目录 ──
        "src/core": "核心数据结构（GameState, Move, Rules）",
        "src/strategy": "策略实现（贪心、MCTS、神经网络等）",
        "src/search": "搜索算法（IS-MCTS, PUCT）",
        "src/analysis": "分析工具（指标、对比、报告生成）",
        "src/rl": "强化学习（自博弈、课程学习）",
        "src/envs": "环境模拟器（牌局生成）",
        "src/iteration": "策略迭代引擎",
        "src/network": "神经网络模型",
        "src/ui": "GUI/Web 界面",
        "src/utils": "通用工具函数",
        # ── src/core/ 文件 ──
        "src/core/types.py": "核心类型定义（GameState, Move 等）",
        "src/core/rules.py": "游戏规则实现",
        "src/core/session.py": "对局会话管理",
        "src/core/info_set.py": "信息集抽象",
        "src/core/manifest.py": "策略清单定义",
        "src/core/exceptions.py": "自定义异常类",
        # ── src/strategy/ 文件 ──
        "src/strategy/registry.py": "策略注册与发现",
        "src/strategy/heuristics.py": "启发式策略（贪心等）",
        "src/strategy/mcts.py": "MCTS 策略实现",
        "src/strategy/neural.py": "神经网络策略",
        "src/strategy/compose.py": "策略组合与切换",
        # ── src/search/ 文件 ──
        "src/search/is_mcts.py": "信息集 MCTS 实现",
        "src/search/puct.py": "PUCT 搜索算法",
        "src/search/determinization.py": "信息集确定化采样",
        # ── src/analysis/ 文件 ──
        "src/analysis/metrics.py": "性能指标计算",
        "src/analysis/runner.py": "分析任务运行器",
        "src/analysis/report.py": "分析报告生成",
        "src/analysis/compare.py": "策略对比分析",
        "src/analysis/batch.py": "批量分析工具",
        "src/analysis/tournament.py": "锦标赛对战分析",
        "src/analysis/genetic.py": "遗传算法优化",
        "src/analysis/tuning.py": "参数调优工具",
        "src/analysis/scenario.py": "场景模拟分析",
        "src/analysis/pattern.py": "牌局模式识别",
        "src/analysis/profile.py": "策略画像生成",
        "src/analysis/factor.py": "因子分析",
        "src/analysis/weakness.py": "弱点检测分析",
        "src/analysis/exporter.py": "分析结果导出",
        "src/analysis/utils.py": "分析工具函数",
        # ── src/rl/ 文件 ──
        "src/rl/environment.py": "RL 环境封装",
        "src/rl/self_play.py": "自博弈训练",
        "src/rl/curriculum.py": "课程学习调度",
        # ── src/envs/ 文件 ──
        "src/envs/generator.py": "牌局生成器",
        "src/envs/simulator.py": "牌局模拟器",
        "src/envs/plugins": "环境插件目录",
        # ── src/iteration/ 文件 ──
        "src/iteration/engine.py": "策略迭代引擎",
        # ── src/network/ 文件 ──
        "src/network/feature_v2.py": "V2 特征提取",
        # ── src/ui/ 文件 ──
        "src/ui/server.py": "Web 服务器",
        "src/ui/window.py": "GUI 窗口管理",
        "src/ui/routes": "Web 路由目录",
        "src/ui/routes/game.py": "对局页面路由",
        "src/ui/routes/analysis.py": "分析页面路由",
        "src/ui/routes/iteration.py": "迭代页面路由",
        "src/ui/routes/export.py": "导出页面路由",
        "src/ui/routes/system.py": "系统页面路由",
        "src/ui/static": "静态资源目录",
        "src/ui/static/index.html": "前端主页",
        # ── src/utils/ 文件 ──
        "src/utils/config.py": "配置文件读取",
        "src/utils/logging.py": "日志配置",
        "src/utils/paths.py": "路径工具函数",
        # ── tests/ 文件 ──
        "tests/conftest.py": "pytest 公共 fixtures",
        "tests/_gen.py": "测试数据生成器",
        "tests/_gen_test.py": "生成器测试",
        "tests/test_rules.py": "规则测试",
        "tests/test_types.py": "类型测试",
        "tests/test_session.py": "会话测试",
        "tests/test_generator.py": "生成器测试",
        "tests/test_simulator.py": "模拟器测试",
        "tests/test_heuristics.py": "启发式策略测试",
        "tests/test_mcts.py": "MCTS 测试",
        "tests/test_neural.py": "神经网络测试",
        "tests/test_compose.py": "策略组合测试",
        "tests/test_registry.py": "策略注册测试",
        "tests/test_search.py": "搜索算法测试",
        "tests/test_analysis.py": "分析模块测试",
        "tests/test_analysis_extended.py": "分析扩展测试",
        "tests/test_iteration.py": "迭代引擎测试",
        "tests/test_rl.py": "强化学习测试",
        "tests/test_server.py": "服务器测试",
        "tests/test_api_match.py": "API 对战测试",
        "tests/test_sync_docs.py": "文档同步测试",
        # ── tools/ 文件 ──
        "tools/sync_docs.py": "文档自动同步脚本",
        "tools/gen_template.py": "模板生成工具",
        "tools/post_improve.py": "代码改进后处理",
        "tools/readme_template.md": "README 模板文件",
        # ── docs/ 文件 ──
        "docs/api.md": "API 接口文档",
        "docs/meta.json": "项目元数据",
        "docs/modules.md": "模块说明文档",
        "docs/project_structure.md": "项目结构文档",
        "docs/strategies.md": "策略说明文档",
        # ── experiments/ 子目录 ──
        "experiments/configs": "实验配置文件（TOML）",
        "experiments/results": "实验输出结果",
        # ── 根目录文件 ──
        "main.py": "程序入口",
        "pyproject.toml": "项目配置与依赖",
        "build.bat": "Windows 打包脚本",
        "Makefile": "构建自动化脚本",
        "config.toml": "运行时配置文件",
        "spiderette.spec": "PyInstaller 打包配置",
        ".gitignore": "Git 忽略规则",
        ".pre-commit-config.yaml": "Pre-commit 钩子配置",
        "LICENSE": "MIT 许可证",
        "README.md": "项目说明（本文件）",
        "更新日志.md": "版本更新记录",
        "法律声明.md": "法律声明与免责条款",
        "算法研究方向.md": "算法研究路线图",
        "项目开发规范.md": "开发规范与约定",
        # ── CI/CD 与构建 ──
        ".github": "GitHub Actions 工作流配置",
        ".github/workflows": "CI/CD 流水线",
        "dist/SpideretteStrategyLab_v5.0.5.exe": "打包输出的可执行文件",
        "dist/spiderette_data": "运行时数据目录",
        "dist/spiderette_data/logs": "运行日志目录",
        "dist/spiderette_data/logs/app.log": "应用日志",
        "dist/spiderette_data/logs/error.log": "错误日志",
        "dist/spiderette_data/logs/strategy.log": "策略日志",
        "dist/spiderette_data/logs/training.log": "训练日志",
        # ── 迭代与清单 ──
        "iterations/.gitkeep": "占位文件",
        "manifests/custom_mcts_v2.json": "自定义 MCTS 策略清单",
        "models/.gitkeep": "占位文件",
        "models/neural_model.npz": "训练好的神经网络模型",
        # ── 工具缓存 ──
        "tools/.file_hashes.json": "文件哈希缓存（增量同步用）",
        "tools/.symbol_snapshots.json": "符号快照缓存（变更检测用）",
    }
    root = PROJECT_ROOT
    lines: list[str] = []

    def _count_lines(path: Path) -> int:
        """统计文件行数"""
        try:
            return len(path.read_text(encoding="utf-8").splitlines())
        except Exception:
            return 0

    def _should_show(name: str) -> bool:
        """判断是否应该显示"""
        return not _should_ignore(name)

    def _get_comment(rel_path: str) -> str:
        """获取路径的中文注释"""
        return _COMMENTS.get(rel_path, "")

    def _walk(path: Path, prefix: str = "", is_last: bool = True, depth: int = 0):
        """递归遍历目录树"""
        entries = sorted(
            [e for e in path.iterdir() if _should_show(e.name)],
            key=lambda e: (not e.is_dir(), e.name),
        )
        for i, entry in enumerate(entries):
            is_entry_last = i == len(entries) - 1
            connector = "└── " if is_entry_last else "├── "
            rel = str(entry.relative_to(root)).replace("\\", "/")

            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                comment = _get_comment(rel)
                if comment:
                    lines[-1] += f"  # {comment}"
                _walk(entry, prefix + ("    " if is_entry_last else "│   "), is_entry_last, depth + 1)
            else:
                line_count = _count_lines(entry)
                lines.append(f"{prefix}{connector}{entry.name}")
                comment = _get_comment(rel)
                if comment:
                    lines[-1] += f"  # {comment}"

    lines.append("Spiderette Strategy Lab/")
    _walk(root, "")

    # ── 右对齐注释：统一注释列 ──
    pairs: list[tuple[str, str]] = []
    for line in lines:
        idx = line.find("  # ")
        if idx != -1:
            pairs.append((line[:idx], line[idx + 2:]))
    if pairs:
        max_tree_width = max(len(t) for t, _ in pairs)
        result: list[str] = []
        pair_iter = iter(pairs)
        current_pair = next(pair_iter, None)
        for line in lines:
            if current_pair and line == current_pair[0] + "  # " + current_pair[1][2:]:
                tree, comment = current_pair
                result.append(f"{tree:<{max_tree_width}}  {comment}")
                current_pair = next(pair_iter, None)
            else:
                result.append(line)
        return chr(10).join(result)
    return chr(10).join(lines)

# ── 元数据构建 ────────────────────────────────────────────────────────────────
def build_meta(modules: list[dict], strategies: list[dict], endpoints: list[dict], test_count: int) -> dict:
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

    changes["test_count_change"] = new_meta.get("test_count", 0) - old_meta.get("test_count", 0)
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


def generate_changelog_entry(version: str, changes: dict, stats: dict, message: str | None = None) -> str:
    """生成变更日志条目"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    lines = [f"## [{version}] - {date_str}", ""]

    if message:
        lines.append(message)
        lines.append("")

    if changes["new_modules"]:
        lines.append("### 新增模块")
        for m in changes["new_modules"]:
            lines.append(f"- `{m}`")
        lines.append("")

    if changes["removed_modules"]:
        lines.append("### 移除模块")
        for m in changes["removed_modules"]:
            lines.append(f"- `{m}`")
        lines.append("")

    if changes["new_strategies"]:
        lines.append("### 新增策略")
        for s in changes["new_strategies"]:
            lines.append(f"- {s}")
        lines.append("")

    if changes["removed_strategies"]:
        lines.append("### 移除策略")
        for s in changes["removed_strategies"]:
            lines.append(f"- {s}")
        lines.append("")

    if changes["new_endpoints"]:
        lines.append("### 新增 API 端点")
        for e in changes["new_endpoints"]:
            lines.append(f"- `{e}`")
        lines.append("")

    if changes["removed_endpoints"]:
        lines.append("### 移除 API 端点")
        for e in changes["removed_endpoints"]:
            lines.append(f"- `{e}`")
        lines.append("")

    if changes["test_count_change"] != 0:
        direction = "增加" if changes["test_count_change"] > 0 else "减少"
        lines.append("### 测试用例变化")
        lines.append(f"- {direction} {abs(changes['test_count_change'])} 个测试用例")
        lines.append("")

    if changes["line_count_change"] != 0:
        direction = "增加" if changes["line_count_change"] > 0 else "减少"
        lines.append("### 代码行数变化")
        lines.append(f"- {direction} {abs(changes['line_count_change'])} 行")
        lines.append("")

    return "\n".join(lines)


def generate_strategy_table(strategies: list[dict]) -> str:
    """生成策略表 Markdown"""
    lines = ["| 策略名称 | 显示名称 | 描述 |", "|----------|----------|------|"]
    for s in strategies:
        lines.append(f"| `{s['name']}` | {s['display_name']} | {s['description']} |")
    return "\n".join(lines)


def generate_api_table(endpoints: list[dict]) -> str:
    """生成 API 端点列表 Markdown"""
    lines = ["| 路径 | 方法 |", "|------|------|"]
    for e in endpoints:
        lines.append(f"| `{e['path']}` | {', '.join(e['methods'])} |")
    return "\n".join(lines)


def generate_module_map(modules: list[dict]) -> str:
    """生成模块地图 Markdown"""
    lines = ["| 路径 | 说明 | 行数 | 类 | 函数 |", "|------|------|------|----|------|"]
    for m in modules:
        lines.append(
            f"| `{m['path']}` | {m['docstring']} | {m['lines']} | {m['classes']} | {m['functions']} |"
        )
    return "\n".join(lines)


def generate_readme(stats: dict, strategies: list[dict], modules: list[dict]) -> str:
    """生成完整 README.md — 从模板替换动态变量，避免 f-string 转义问题"""
    template_file = TOOLS_DIR / "readme_template.md"
    if not template_file.exists():
        return ""

    template = template_file.read_text(encoding="utf-8")

    # 构建替换字典 — 键名与 readme_template.md 中的 {{变量名}} 一一对应
    project_meta = _read_project_meta()
    default_name = project_meta.get("display_name") or project_meta.get("name", "Spiderette Strategy Lab")
    first_strategy = strategies[0]["name"] if strategies else "mcts"
    replacements = {
        "{{PROJECT_NAME}}": default_name,
        "{{version}}": stats.get("version", _read_version()),
        "{{total_modules}}": str(stats.get("total_modules", 0)),
        "{{total_strategies}}": str(stats.get("total_strategies", 0)),
        "{{total_endpoints}}": str(stats.get("total_endpoints", 0)),
        "{{test_count}}": str(stats.get("test_count", 0)),
        "{{total_lines}}": f"{stats.get('total_lines', 0):,}",
        "{{arch_str}}": scan_full_project_tree(),
        "{{strat_table}}": generate_strategy_table(strategies),
        "{{strat_example_first}}": first_strategy,
    }

    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)

    # 清理：scan_full_project_tree 可能从 README.md 读入残留的 {{变量}}
    import re
    result = re.sub(r'\{\{\w+\}\}', '', result)

    return result


# ── 主同步流程 ────────────────────────────────────────────────────────────────
def sync_all(
    check_only: bool = False,
    message: str | None = None,
    bump_version: str | None = None,
    no_changelog: bool = False,
    no_git: bool = False,
) -> bool:
    """同步所有文档"""
    print("[sync_docs] 开始同步文档...")

    # 扫描数据
    modules = scan_modules()
    strategies = scan_strategy_registry()
    endpoints = scan_api_endpoints()
    test_count = scan_test_count()

    # 构建新元数据
    new_meta = build_meta(modules, strategies, endpoints, test_count)

    # 加载旧元数据
    meta_file = DOCS_DIR / "meta.json"
    if meta_file.exists():
        try:
            old_meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            old_meta = {}
    else:
        old_meta = {}

    # 检测变化
    changes = detect_changes(old_meta, new_meta)

    if check_only:
        if has_changes(changes):
            print("[sync_docs] 检测到变化，需要同步")
            return True
        else:
            print("[sync_docs] 无变化")
            return False

    # 版本递增
    if bump_version:
        current = _read_version()
        if bump_version == "major":
            parts = current.split(".")
            parts[0] = str(int(parts[0]) + 1)
            parts[1] = "0"
            parts[2] = "0"
            new_version = ".".join(parts)
        elif bump_version == "minor":
            parts = current.split(".")
            parts[1] = str(int(parts[1]) + 1)
            parts[2] = "0"
            new_version = ".".join(parts)
        else:
            new_version = _next_version(current)
        new_meta["version"] = new_version

    # 写入 meta.json
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(new_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[sync_docs] 已更新 docs/meta.json")

    # 生成策略表
    strategy_table = generate_strategy_table(strategies)
    (DOCS_DIR / "strategies.md").write_text(strategy_table, encoding="utf-8")
    print("[sync_docs] 已更新 docs/strategies.md")

    # 生成 API 表
    api_table = generate_api_table(endpoints)
    (DOCS_DIR / "api.md").write_text(api_table, encoding="utf-8")
    print("[sync_docs] 已更新 docs/api.md")

    # 生成模块地图
    module_map = generate_module_map(modules)
    (DOCS_DIR / "modules.md").write_text(module_map, encoding="utf-8")
    print("[sync_docs] 已更新 docs/modules.md")

    # 生成 README
    readme_content = generate_readme({**new_meta["stats"], "test_count": new_meta["test_count"]}, strategies, modules)
    if readme_content:
        (PROJECT_ROOT / "README.md").write_text(readme_content, encoding="utf-8")
        print("[sync_docs] 已更新 README.md")

    # 更新日志
    if not no_changelog and has_changes(changes):
        entry = generate_changelog_entry(
            new_meta.get("version", _read_version()),
            changes,
            new_meta.get("stats", {}),
            message,
        )
        if entry.strip():
            with open(CHANGELOG_FILE, "a", encoding="utf-8") as f:
                f.write("\n" + entry + "\n")
            print("[sync_docs] 已更新 更新日志.md")
    else:
        print("[sync_docs] 更新日志由人工维护，跳过")

    # 保存文件哈希
    current_hashes = _scan_current_hashes()
    _save_hashes(current_hashes)

    # 保存符号快照
    snapshots: dict[str, dict] = {}
    for m in modules:
        full_path = PROJECT_ROOT / m["path"]
        if full_path.exists():
            snapshots[m["path"]] = _extract_ast_symbols(full_path)
    _save_symbol_snapshots(snapshots)

    # Git 提交
    if no_git:
        print("[sync_docs] 跳过 Git 操作（--no-git）")
    else:
        files_to_commit = [
            "docs/meta.json",
            "docs/strategies.md",
            "docs/api.md",
            "docs/modules.md",
            "README.md",
            "更新日志.md",
        ]
        commit_msg = f"docs: 自动同步文档 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"
        if _git_add_and_commit(commit_msg, files_to_commit):
            print("✅ 已提交到 Git")
        else:
            print("⚠️  Git 提交跳过（无变更或失败）")
            print("⚠️  Git 提交跳过（无变更或失败）")

    print("[sync_docs] 同步完成")
    return True


def _bump_version(current: str, level: str) -> str:
    """递增版本号"""
    parts = current.split(".")
    if level == "major":
        parts[0] = str(int(parts[0]) + 1)
        parts[1] = "0"
        parts[2] = "0"
    elif level == "minor":
        parts[1] = str(int(parts[1]) + 1)
        parts[2] = "0"
    else:
        parts[2] = str(int(parts[2]) + 1)
    return ".".join(parts)


def _get_changelog_latest_version() -> str:
    """从更新日志获取最新版本号"""
    if not CHANGELOG_FILE.exists():
        return "0.0.0"
    try:
        content = CHANGELOG_FILE.read_text(encoding="utf-8")
        match = re.search(r"## \[(\d+\.\d+\.\d+)\]", content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "0.0.0"


# ── CLI 入口 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="文档自动同步工具")
    parser.add_argument("--check", action="store_true", help="检查是否有差异（CI 模式）")
    parser.add_argument("--message", type=str, help="手动指定变更描述")
    parser.add_argument(
        "--bump-version",
        choices=["major", "minor", "patch"],
        help="强制版本递增",
    )
    parser.add_argument("--no-changelog", action="store_true", help="跳过更新日志")
    parser.add_argument("--no-git", action="store_true", help="跳过 git 操作")
    args = parser.parse_args()

    sync_all(
        check_only=args.check,
        message=args.message,
        bump_version=args.bump_version,
        no_changelog=args.no_changelog,
        no_git=args.no_git,
    )
