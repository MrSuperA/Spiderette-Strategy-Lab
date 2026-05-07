"""
多策略并行对比 — 同 seed 多策略运行，实时对比决策差异
核心能力：公平对比（同一牌局）、并行执行、差异分析
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from src.core.session import GameResult, GameSession, StepRecord
from src.core.types import GameState, Strategy
from src.envs.simulator import SimulatorEnv
from src.strategy.registry import get_strategy
from src.analysis.metrics import StrategyStats, collect_stats, DistributionStats
from src.analysis.utils import run_single_game


@dataclass
class ComparisonStep:
    """单步对比数据"""
    step: int
    strategy_name: str
    action: str              # "move"/"deal"/"complete"
    src_col: int = -1
    dst_col: int = -1
    top_card: str = ""
    completed: int = 0
    stock_remaining: int = 0


@dataclass
class GameComparison:
    """单局多策略对比结果"""
    seed: int
    difficulty: int
    results: dict[str, GameResult] = field(default_factory=dict)
    step_logs: dict[str, list[ComparisonStep]] = field(default_factory=dict)

    @property
    def winner(self) -> Optional[str]:
        """谁完成了更多序列"""
        best = max(self.results.items(), key=lambda x: x[1].completed)
        return best[0] if best[1].completed > 0 else None

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "difficulty": self.difficulty,
            "winner": self.winner,
            "strategies": {
                name: {
                    "outcome": r.outcome.name.lower(),
                    "completed": r.completed,
                    "total_moves": r.total_moves,
                    "total_time_ms": round(r.total_time_ms, 2),
                }
                for name, r in self.results.items()
            },
        }


@dataclass
class ComparisonReport:
    """多策略对比报告"""
    strategy_names: list[str]
    difficulty: int
    comparisons: list[GameComparison] = field(default_factory=list)
    stats: dict[str, StrategyStats] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategies": self.strategy_names,
            "difficulty": self.difficulty,
            "total_games": len(self.comparisons),
            "stats": {name: s.to_dict() for name, s in self.stats.items()},
            "comparisons": [c.to_dict() for c in self.comparisons],
            "rankings": self._compute_rankings(),
        }

    def _compute_rankings(self) -> dict:
        """计算排名"""
        if not self.stats:
            return {}
        best_win = max(self.stats.items(), key=lambda x: x[1].win_rate)
        best_eff = max(self.stats.items(), key=lambda x: x[1].avg_move_efficiency)
        best_moves = min(
            ((n, s) for n, s in self.stats.items() if s.wins > 0),
            key=lambda x: x[1].avg_moves,
            default=(best_win[0], best_win[1]),
        )
        return {
            "best_win_rate": {"name": best_win[0], "rate": round(best_win[1].win_rate, 4)},
            "best_efficiency": {"name": best_eff[0], "value": round(best_eff[1].avg_move_efficiency, 4)},
            "best_avg_moves": {"name": best_moves[0], "value": round(best_moves[1].avg_moves, 1)},
        }


class ParallelStrategyRunner:
    """
    多策略并行对比运行器

    用法::

        runner = ParallelStrategyRunner()
        report = runner.compare(
            strategy_names=["greedy", "mcts"],
            difficulty=1,
            seeds=range(1, 51),
        )
    """

    def __init__(self, on_progress: Optional[callable] = None):
        self._on_progress = on_progress

    def compare(
        self,
        strategy_names: list[str],
        difficulty: int = 1,
        seeds: list[int] | range = range(1, 51),
        max_moves: int = 500,
        parallel: bool = True,
    ) -> ComparisonReport:
        """
        同 seed 多策略并行对比

        Args:
            strategy_names: 策略名列表
            difficulty: 难度
            seeds: 种子列表
            max_moves: 每局最大步数
            parallel: 是否并行（False 时串行执行）

        Returns:
            ComparisonReport 对比报告
        """
        seeds = list(seeds)
        report = ComparisonReport(
            strategy_names=strategy_names,
            difficulty=difficulty,
        )

        total = len(seeds)
        done = 0

        for seed in seeds:
            comparison = self._compare_single(
                seed=seed,
                difficulty=difficulty,
                strategy_names=strategy_names,
                max_moves=max_moves,
                parallel=parallel,
            )
            report.comparisons.append(comparison)

            done += 1
            if self._on_progress:
                self._on_progress({
                    "done": done,
                    "total": total,
                    "seed": seed,
                    "winner": comparison.winner,
                })

        # 聚合统计
        for name in strategy_names:
            results = [c.results[name] for c in report.comparisons if name in c.results]
            report.stats[name] = collect_stats(name, results)

        return report

    def _compare_single(
        self,
        seed: int,
        difficulty: int,
        strategy_names: list[str],
        max_moves: int,
        parallel: bool,
    ) -> GameComparison:
        """单局多策略对比"""
        comparison = GameComparison(seed=seed, difficulty=difficulty)

        if parallel and len(strategy_names) > 1:
            # 并行执行
            with ProcessPoolExecutor(max_workers=len(strategy_names)) as executor:
                futures = {}
                for name in strategy_names:
                    futures[executor.submit(
                        _run_single_game, seed, difficulty, name, max_moves
                    )] = name

                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        comparison.results[name] = future.result()
                    except Exception as e:
                        from src.core.types import Outcome
                        comparison.results[name] = GameResult(
                            outcome=Outcome.DEADLOCK,
                            seed=seed,
                            total_moves=0,
                            total_time_ms=0.0,
                            completed=0,
                            steps=[],
                        )
        else:
            # 串行执行
            for name in strategy_names:
                comparison.results[name] = self._run_game(seed, difficulty, name, max_moves)

        return comparison

    def _run_game(
        self, seed: int, difficulty: int, strategy_name: str, max_moves: int
    ) -> GameResult:
        """运行单局"""
        strategy = get_strategy(strategy_name)
        return run_single_game(seed, difficulty, strategy, max_moves)


def _run_single_game(seed: int, difficulty: int, strategy_name: str, max_moves: int) -> GameResult:
    """独立函数，供 ProcessPoolExecutor 调用"""
    from src.strategy.registry import get_strategy
    strategy = get_strategy(strategy_name)
    return run_single_game(seed, difficulty, strategy, max_moves)
