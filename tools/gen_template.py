"""
模板生成工具 — 从当前 README.md 生成 readme_template.md

设计原则：
  README.md 是「活文档」，由 sync_docs.py 自动更新策略表、统计数字等。
  本工具从当前 README 提取结构，将具体数值替换为占位符，生成模板文件。
  sync_docs.py 后续用模板 + 实时数据重建 README，保证格式一致。

替换规则：
  - 版本号 v1.2.3 → {{version}}
  - 统计行 "8 模块 · 8 策略 · ..." → {{total_modules}} 模块 · ...
  - 策略名 (random/greedy/mcts 等) → {{strat_example_first}}
  - 项目结构树 → {{arch_str}}
  - 策略表格（表头+数据行）→ {{strat_table}}
  - 源码行数、测试项数、端点数 → 对应占位符

用法：
    python tools/gen_template.py

输出：
    tools/readme_template.md — 带占位符的 README 模板

依赖：
  - 需要 README.md 存在且包含当前格式的策略表和统计行
  - 占位符格式与 sync_docs.py 中的 _build_readme_from_template() 对应
"""

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
README = PROJECT_ROOT / "README.md"
TEMPLATE = PROJECT_ROOT / "tools" / "readme_template.md"


def _find_block(text: str, start_marker: str, is_line_pred) -> tuple[int, int]:
    """在 text 中找到以 start_marker 开头的连续块，返回 (block_start, block_end)。

    Args:
        text: 完整文本
        start_marker: 块起始标记（如树根 "Spiderette Strategy Lab/"）
        is_line_pred: 判断下一行是否属于同一块的谓词函数

    Returns:
        (block_start, block_end) 字符索引范围，block_end 是块后第一行的起始
    """
    marker_pos = text.find(start_marker)
    if marker_pos <= 0:
        return (-1, -1)

    # 找到块起始行的行首
    line_start = text.rfind(chr(10), 0, marker_pos)
    line_start = 0 if line_start < 0 else line_start + 1

    # 向下扫描，找到块结束位置
    search_from = marker_pos
    while True:
        idx = text.find(chr(10), search_from)
        if idx < 0:
            return (line_start, len(text))
        next_line_start = idx + 1
        if next_line_start >= len(text):
            return (line_start, idx)
        if is_line_pred(text, next_line_start):
            search_from = idx + 1
        else:
            return (line_start, idx)


def _is_tree_line(text: str, pos: int) -> bool:
    """判断 pos 处的行是否属于项目结构树（以空格/│/├/└ 开头）"""
    ch = text[pos:pos + 1]
    return ch in (" ", "│", "├", "└")


def _is_table_line(text: str, pos: int) -> bool:
    """判断 pos 处的行是否属于 Markdown 表格（以 | 或 --- 开头）"""
    line = text[pos:pos + 20].strip()
    return line.startswith("|") or line.startswith("---")


def generate_template():
    """从 README.md 生成 readme_template.md 模板。

    读取当前 README，用正则和字符串替换将具体数值转为占位符，
    写入 tools/readme_template.md。
    """
    with open(README, "r", encoding="utf-8") as f:
        readme = f.read()

    t = readme

    # 1. 版本号 → {{version}}
    t = re.sub(r"\*\*v[\d.]+\*\*", "**v{{version}}**", t)

    # 2. 统计行 → 占位符
    t = re.sub(
        r"\d+ 模块 · \d+ 策略 · \d+ API · \d+ 测试 · [\d,]+ 行代码",
        "{{total_modules}} 模块 · {{total_strategies}} 策略 · {{total_endpoints}} API · {{test_count}} 测试 · {{total_lines}} 行代码",
        t,
    )

    # 3. 策略名 → {{strat_example_first}}
    STRATS = ["random", "greedy", "mcts_deep", "mcts_fast", "mcts", "is_mcts", "neural", "puct"]
    for s in STRATS:
        t = t.replace("--strategy " + s, "--strategy {{strat_example_first}}")
        t = t.replace("get_strategy(" + repr(s) + ")", "get_strategy({{strat_example_first}})")
        t = t.replace("strategy=" + s, "strategy={{strat_example_first}}")

    # 4. 项目结构树 → {{arch_str}}
    start, end = _find_block(t, "Spiderette Strategy Lab/", _is_tree_line)
    if start >= 0:
        t = t[:start] + "{{arch_str}}" + chr(10) + t[end:]

    # 5. 策略表格 → {{strat_table}}
    table_header = "| 策略名称 | 显示名称 | 描述 |"
    start, end = _find_block(t, table_header, _is_table_line)
    if start >= 0:
        t = t[:start] + "{{strat_table}}" + chr(10) + t[end:]

    # 6. 其他统计数字
    t = re.sub(r"源码，按四层架构组织（[\d,]+ 行）", "源码，按四层架构组织（{{total_lines}} 行）", t)
    t = re.sub(r"测试套件（\d+ 项）", "测试套件（{{test_count}} 项）", t)
    t = re.sub(r"共 \d+ 个端点", "共 {{total_endpoints}} 个端点", t)

    with open(TEMPLATE, "w", encoding="utf-8") as f:
        f.write(t)

    print(f"Written {len(t)} chars, {t.count(chr(10))} lines")


if __name__ == "__main__":
    generate_template()
