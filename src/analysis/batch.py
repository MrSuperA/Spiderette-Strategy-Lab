"""
批量模拟 — 多进程并行执行
独立模块，可被 ProcessPoolExecutor 子进程安全调用
"""

from __future__ import annotations

from src.core.types import Strategy
from src.analysis.utils import run_single_game, _run_game_for_pool


def run_single_game_dict(args: tuple[int, int, str, int]) -> dict:
    """
    运行单局游戏 — 供 ProcessPoolExecutor 调用（返回字典格式）

    Args:
        args: (seed, difficulty, strategy_name, max_moves)

    Returns:
        单局结果字典
    """
    seed, difficulty, strategy_name, max_moves = args
    result = _run_game_for_pool(args)

    return {
        "seed": seed,
        "result": "WIN" if result.completed >= 8 else "DEAD",
        "completed": result.completed,
        "total_steps": result.total_moves,
        "duration": result.total_time_ms,
        "strategy": strategy_name,
    }


def run_batch_parallel(
    strategy_name: str,
    difficulty: int,
    count: int,
    max_moves: int = 500,
    max_workers: int | None = None,
) -> list[dict]:
    """
    多进程并行运行批量模拟

    Args:
        strategy_name: 策略名
        difficulty: 难度 (1/2/4)
        count: 局数
        max_moves: 每局最大步数
        max_workers: 并行进程数（默认 CPU 核心数）

    Returns:
        结果列表
    """
    from concurrent.futures import ProcessPoolExecutor

    tasks = [(i + 1, difficulty, strategy_name, max_moves) for i in range(count)]

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(run_single_game_dict, tasks))

    return results
