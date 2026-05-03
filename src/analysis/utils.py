"""
分析层公共工具函数 — 消除模块间重复代码
设计原则：纯函数，无状态，所有分析模块共享
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Optional, Sequence

from src.core.session import GameResult, GameSession
from src.core.types import Strategy
from src.envs.simulator import SimulatorEnv


def run_single_game(
    seed: int,
    difficulty: int,
    strategy: Strategy,
    max_moves: int = 500,
) -> GameResult:
    """
    运行单局游戏 — 消除 6 处重复的 "env→session→run" 模式

    Args:
        seed: 牌局种子
        difficulty: 难度 (1/2/4)
        strategy: 策略实例
        max_moves: 每局最大步数

    Returns:
        GameResult
    """
    env = SimulatorEnv(seed=seed, difficulty=difficulty)
    session = GameSession(env, strategy, max_moves=max_moves)
    return session.run()


def run_games_batch(
    strategy: Strategy,
    seeds: Sequence[int],
    difficulty: int = 1,
    max_moves: int = 500,
    on_progress: Optional[callable] = None,
    strategy_name: str = "",
) -> list[GameResult]:
    """
    批量运行多局游戏（串行）

    Args:
        strategy: 策略实例
        seeds: 种子列表
        difficulty: 难度
        max_moves: 每局最大步数
        on_progress: 进度回调
        strategy_name: 策略名（用于进度回调）

    Returns:
        GameResult 列表
    """
    results = []
    total = len(seeds)
    for i, seed in enumerate(seeds):
        result = run_single_game(seed, difficulty, strategy, max_moves)
        results.append(result)
        if on_progress:
            on_progress({
                "strategy": strategy_name,
                "seed": seed,
                "done": i + 1,
                "total": total,
                "outcome": result.outcome.name.lower(),
            })
    return results


def _run_game_for_pool(args: tuple[int, int, str, int]) -> GameResult:
    """供 ProcessPoolExecutor 调用的独立函数（必须在模块顶层定义）"""
    seed, difficulty, strategy_name, max_moves = args
    from src.strategy.registry import get_strategy
    strategy = get_strategy(strategy_name)
    return run_single_game(seed, difficulty, strategy, max_moves)


def run_games_parallel(
    strategy_name: str,
    seeds: Sequence[int],
    difficulty: int = 1,
    max_moves: int = 500,
    max_workers: Optional[int] = None,
) -> list[GameResult]:
    """
    多进程并行运行批量游戏

    Args:
        strategy_name: 策略名（必须是注册中心中的名称）
        seeds: 种子列表
        difficulty: 难度
        max_moves: 每局最大步数
        max_workers: 并行进程数

    Returns:
        GameResult 列表
    """
    tasks = [(seed, difficulty, strategy_name, max_moves) for seed in seeds]
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(_run_game_for_pool, tasks))
