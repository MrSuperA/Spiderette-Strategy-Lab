"""
策略参数自动调优 — 网格搜索 + 贝叶斯优化
自动寻找最优参数组合，平衡区域最优和全局效率
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from src.core.session import GameResult, GameSession
from src.core.types import Strategy
from src.envs.simulator import SimulatorEnv
from src.strategy.registry import get_strategy
from src.analysis.metrics import StrategyStats, collect_stats
from src.analysis.utils import run_single_game, run_games_batch


@dataclass
class ParamConfig:
    """参数搜索空间"""
    name: str
    values: list            # 网格搜索的候选值


@dataclass
class TrialResult:
    """单次试验结果"""
    params: dict
    win_rate: float
    avg_moves: float
    avg_completed: float
    avg_efficiency: float
    total_games: int

    def to_dict(self) -> dict:
        return {
            "params": self.params,
            "win_rate": round(self.win_rate, 4),
            "avg_moves": round(self.avg_moves, 1),
            "avg_completed": round(self.avg_completed, 2),
            "avg_efficiency": round(self.avg_efficiency, 4),
            "total_games": self.total_games,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TrialResult:
        return cls(
            params=data["params"],
            win_rate=data.get("win_rate", 0.0),
            avg_moves=data.get("avg_moves", 0.0),
            avg_completed=data.get("avg_completed", 0.0),
            avg_efficiency=data.get("avg_efficiency", 0.0),
            total_games=data.get("total_games", 0),
        )


@dataclass
class TuningReport:
    """调优报告"""
    strategy_name: str
    search_space: list[dict]
    trials: list[TrialResult] = field(default_factory=list)
    best_params: dict = field(default_factory=dict)
    best_score: float = 0.0
    baseline_score: float = 0.0
    improvement: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "n_trials": len(self.trials),
            "best_params": self.best_params,
            "best_score": round(self.best_score, 4),
            "baseline_score": round(self.baseline_score, 4),
            "improvement": round(self.improvement, 4),
            "trials": [t.to_dict() for t in self.trials],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TuningReport:
        return cls(
            strategy_name=data.get("strategy", data.get("strategy_name", "")),
            search_space=data.get("search_space", []),
            trials=[TrialResult.from_dict(t) for t in data.get("trials", [])],
            best_params=data.get("best_params", {}),
            best_score=data.get("best_score", 0.0),
            baseline_score=data.get("baseline_score", 0.0),
            improvement=data.get("improvement", 0.0),
        )


class ParameterTuner:
    """
    策略参数自动调优器

    用法::

        tuner = ParameterTuner()
        report = tuner.tune(
            strategy_name="mcts",
            param_space=[
                ParamConfig("iterations", [100, 200, 500, 1000]),
                ParamConfig("time_limit", [0.1, 0.2, 0.5, 1.0]),
            ],
            difficulty=1,
            num_games=20,
        )
    """

    def __init__(self, on_progress: Optional[callable] = None):
        self._on_progress = on_progress

    def tune(
        self,
        strategy_name: str,
        param_space: list[ParamConfig],
        difficulty: int = 1,
        num_games: int = 20,
        seeds: Optional[list[int]] = None,
        max_moves: int = 500,
        scoring: str = "win_rate",
    ) -> TuningReport:
        """
        网格搜索调优

        Args:
            strategy_name: 策略名
            param_space: 参数搜索空间
            difficulty: 难度
            num_games: 每组参数的游戏数
            seeds: 种子列表（保证公平对比）
            max_moves: 每局最大步数
            scoring: 评分标准 ("win_rate"/"avg_completed"/"efficiency")

        Returns:
            TuningReport
        """
        if seeds is None:
            seeds = list(range(1, num_games + 1))

        # 生成参数组合
        param_names = [p.name for p in param_space]
        param_values = [p.values for p in param_space]
        combinations = list(itertools.product(*param_values))

        report = TuningReport(
            strategy_name=strategy_name,
            search_space=[
                {p.name: p.values for p in param_space}
            ],
        )

        # 基线（默认参数）
        baseline = self._evaluate(strategy_name, {}, difficulty, seeds, max_moves)
        report.baseline_score = self._get_score(baseline, scoring)

        total = len(combinations)
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))

            result = self._evaluate(strategy_name, params, difficulty, seeds, max_moves)
            score = self._get_score(result, scoring)

            trial = TrialResult(
                params=params,
                win_rate=result.win_rate,
                avg_moves=result.avg_moves,
                avg_completed=result.avg_completed,
                avg_efficiency=result.avg_move_efficiency,
                total_games=result.total_games,
            )
            report.trials.append(trial)

            if score > report.best_score:
                report.best_score = score
                report.best_params = params

            if self._on_progress:
                self._on_progress({
                    "trial": i + 1,
                    "total": total,
                    "params": params,
                    "score": round(score, 4),
                    "best": round(report.best_score, 4),
                })

        report.improvement = report.best_score - report.baseline_score
        return report

    def _evaluate(
        self,
        strategy_name: str,
        params: dict,
        difficulty: int,
        seeds: list[int],
        max_moves: int,
    ) -> StrategyStats:
        """评估一组参数"""
        strategy = get_strategy(strategy_name, **params)
        results = run_games_batch(strategy, seeds, difficulty, max_moves)
        return collect_stats(strategy_name, results)

    def _get_score(self, stats: StrategyStats, scoring: str) -> float:
        """获取评分"""
        if scoring == "win_rate":
            return stats.win_rate
        elif scoring == "avg_completed":
            return stats.avg_completed
        elif scoring == "efficiency":
            return stats.avg_move_efficiency
        return stats.win_rate

    def apply_best(self, report: TuningReport) -> Strategy:
        """根据调优报告的最优参数创建策略实例"""
        return get_strategy(report.strategy_name, **report.best_params)

    def export(self, report: TuningReport, output_dir: str | Path) -> Path:
        """导出调优报告"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = out / f"tuning_{report.strategy_name}_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        # TXT
        txt_path = out / f"tuning_{report.strategy_name}_{datetime.now():%Y%m%d_%H%M%S}.txt"
        lines = []
        lines.append("=" * 60)
        lines.append(f"  策略参数调优报告 — {report.strategy_name}")
        lines.append("=" * 60)
        lines.append(f"  试验次数: {len(report.trials)}")
        lines.append(f"  基线得分: {report.baseline_score:.4f}")
        lines.append(f"  最优得分: {report.best_score:.4f}")
        lines.append(f"  提升幅度: {report.improvement:+.4f}")
        lines.append("")
        lines.append(f"  最优参数: {report.best_params}")
        lines.append("")
        lines.append(f"  {'参数':<20} {'胜率':>8} {'均步数':>8} {'均完成':>8} {'效率':>8}")
        lines.append(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
        for trial in sorted(report.trials, key=lambda t: -t.win_rate):
            params_str = str(trial.params)
            lines.append(
                f"  {params_str:<20} {trial.win_rate:>7.1%} {trial.avg_moves:>7.0f} "
                f"{trial.avg_completed:>7.1f} {trial.avg_efficiency:>7.4f}"
            )
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return json_path
