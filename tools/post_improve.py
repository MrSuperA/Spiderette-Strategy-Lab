"""
改进后自动化脚本 — 测试 → 同步文档 → 可选提交

设计原则：
  改进代码后一键执行，确保文档与代码同步。
  本脚本是 post-improve 流程的唯一入口，协调测试、文档同步和 Git 提交。

核心流程：
  1. 运行测试套件（pytest）— 确保代码质量
  2. 同步文档（调用 sync_docs.py --no-git）— 更新 README、策略表、API 等
  3. 可选 Git 提交（--commit）— 统一由本脚本处理，sync_docs 不直接操作 Git

与 sync_docs.py 的关系：
  - sync_docs.py 负责文档内容生成，通过 --no-git 跳过 Git 操作
  - 本脚本负责流程编排和 Git 提交，避免两个脚本各自提交导致冲突

用法：
    python tools/post_improve.py                    # 测试 + 同步
    python tools/post_improve.py --message "描述"    # 测试 + 同步 + 自定义变更描述
    python tools/post_improve.py --skip-tests        # 跳过测试，只同步
    python tools/post_improve.py --bump minor        # 强制版本递增
    python tools/post_improve.py --commit            # 同步后自动 git add + commit
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).parent.parent


def run_tests() -> bool:
    """运行测试套件（pytest -x -q --tb=short）

    Returns:
        True 如果所有测试通过，False 如果有失败
    """
    print("=" * 60)
    print("[post_improve] 运行测试...")
    print("=" * 60)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--tb=short"],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
        env={**__import__("os").environ, "PYTHONUTF8": "1"},
    )

    if result.returncode != 0:
        print(f"\n[post_improve] \u274c 测试失败（退出码 {result.returncode}）")
        print("[post_improve] 修复测试后再同步文档")
        return False

    print("\n[post_improve] \u2705 测试全部通过")
    return True


def run_sync(
    message: str | None = None,
    bump: str | None = None,
    skip_changelog: bool = False,
) -> bool:
    """运行文档同步（调用 sync_docs.py --no-git）

    Args:
        message: 自定义变更描述，传给 sync_docs.py --message
        bump: 版本递增级别（major/minor/patch），传给 sync_docs.py --bump-version
        skip_changelog: 是否跳过更新日志生成

    Returns:
        True 如果同步成功，False 如果失败
    """
    print("\n" + "=" * 60)
    print("[post_improve] 同步文档...")
    print("=" * 60)

    args = [sys.executable, str(PROJECT_ROOT / "tools" / "sync_docs.py")]

    if message:
        args.extend(["--message", message])
    if bump:
        args.extend(["--bump-version", bump])
    if skip_changelog:
        args.append("--no-changelog")

    args.append("--no-git")  # git 由 post_improve 统一处理
    result = subprocess.run(args, cwd=str(PROJECT_ROOT), env={**__import__("os").environ, "PYTHONUTF8": "1"})

    if result.returncode != 0:
        print("\n[post_improve] \u274c 文档同步失败")
        return False

    return True


def git_commit(message: str | None = None) -> bool:
    """Git add + commit 所有变更

    流程：
      1. 检查 git 是否可用
      2. git add -A（暂存所有变更）
      3. 检查是否有实际变更（git diff --cached --quiet）
      4. 生成 commit message 并提交

    Args:
        message: 自定义 commit message，为空则自动生成带时间戳的消息

    Returns:
        True 如果提交成功或无变更需要提交
    """
    print("\n" + "=" * 60)
    print("[post_improve] Git 提交...")
    print("=" * 60)

    # 检查 git 是否可用
    try:
        subprocess.run(
            ["git", "status"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[post_improve] \u26a0\ufe0f  Git 不可用，跳过提交")
        return True

    # git add
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(PROJECT_ROOT),
    )

    # 检查是否有变更
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode == 0:
        print("[post_improve] 无变更需要提交")
        return True

    # 生成 commit message
    if not message:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        message = f"docs: auto-sync {now}"

    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(PROJECT_ROOT),
    )

    print(f"[post_improve] \u2705 已提交: {message}")
    return True


def main():
    """CLI 入口 — 解析参数并按顺序执行 测试 → 同步 → 提交"""
    skip_tests = "--skip-tests" in sys.argv
    do_commit = "--commit" in sys.argv
    message = None
    bump = None

    if "--message" in sys.argv:
        idx = sys.argv.index("--message")
        if idx + 1 < len(sys.argv):
            message = sys.argv[idx + 1]

    if "--bump" in sys.argv:
        idx = sys.argv.index("--bump")
        if idx + 1 < len(sys.argv):
            bump = sys.argv[idx + 1]

    print(f"[post_improve] 开始改进后自动化流程 ({datetime.now():%Y-%m-%d %H:%M:%S})")
    print()

    # Step 1: 测试
    if not skip_tests:
        if not run_tests():
            sys.exit(1)
    else:
        print("[post_improve] 跳过测试")

    # Step 2: 同步文档
    if not run_sync(message=message, bump=bump):
        sys.exit(1)

    # Step 3: 可选 git 提交
    if do_commit:
        git_commit(message)

    print("\n" + "=" * 60)
    print("[post_improve] \u2705 改进后自动化流程完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
