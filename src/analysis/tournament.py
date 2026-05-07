"""
策略对抗 — 锦标赛模式：同 seed 多策略对比，生成胜率矩阵
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.session import GameSession
from src.envs.simulator import SimulatorEnv
from src.strategy.registry import get_strategy
from src.analysis.utils import run_single_game


@dataclass
class MatchResult:
    """一对策略的对比结果"""
    strategy_a: str
    strategy_b: str
    wins_a: int = 0
    wins_b: int = 0
    draws: int = 0
    total: int = 0

    @property
    def win_rate_a(self) -> float:
        return self.wins_a / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {"a": self.strategy_a, "b": self.strategy_b,
                "wins_a": self.wins_a, "wins_b": self.wins_b,
                "draws": self.draws, "total": self.total,
                "win_rate_a": round(self.win_rate_a, 4)}


@dataclass
class TournamentResult:
    """锦标赛结果"""
    strategies: list[str]
    difficulty: int
    matches: list[MatchResult] = field(default_factory=list)
    standings: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"strategies": self.strategies, "difficulty": self.difficulty,
                "matches": [m.to_dict() for m in self.matches],
                "standings": self.standings}


class Tournament:
    """
    策略锦标赛

    每对策略在同一组种子上对比，统计谁完成更多序列。

    用法::

        t = Tournament()
        result = t.run(["greedy", "mcts", "mcts_fast"], difficulty=1, seeds=range(1, 21))
    """

    def __init__(self, on_progress: Optional[callable] = None):
        self._on_progress = on_progress

    def run(
        self,
        strategy_names: list[str],
        difficulty: int = 1,
        seeds: list[int] | range = range(1, 21),
        max_moves: int = 500,
    ) -> TournamentResult:
        seeds = list(seeds)
        result = TournamentResult(strategies=strategy_names, difficulty=difficulty)

        # 预构建策略实例
        strategies = {name: get_strategy(name) for name in strategy_names}

        # 预运行所有策略+种子组合
        cache: dict[tuple[str, int], int] = {}  # (strategy, seed) → completed
        total = len(strategy_names) * len(seeds)
        done = 0

        for name in strategy_names:
            for seed in seeds:
                game_result = run_single_game(seed, difficulty, strategies[name], max_moves)
                cache[(name, seed)] = game_result.completed
                done += 1
                if self._on_progress:
                    self._on_progress({"phase": "running", "done": done, "total": total})

        # 两两对比
        for i, a in enumerate(strategy_names):
            for j, b in enumerate(strategy_names):
                if i >= j:
                    continue
                match = MatchResult(strategy_a=a, strategy_b=b)
                for seed in seeds:
                    ca, cb = cache[(a, seed)], cache[(b, seed)]
                    if ca > cb:
                        match.wins_a += 1
                    elif cb > ca:
                        match.wins_b += 1
                    else:
                        match.draws += 1
                    match.total += 1
                result.matches.append(match)

        # 计算排名
        standings = {name: {"wins": 0, "total": 0, "score": 0.0} for name in strategy_names}
        for match in result.matches:
            standings[match.strategy_a]["wins"] += match.wins_a
            standings[match.strategy_a]["total"] += match.total
            standings[match.strategy_b]["wins"] += match.wins_b
            standings[match.strategy_b]["total"] += match.total

        for name, s in standings.items():
            s["win_rate"] = round(s["wins"] / s["total"], 4) if s["total"] > 0 else 0
            s["score"] = s["win_rate"]

        # 按得分排序
        result.standings = dict(sorted(standings.items(), key=lambda x: -x[1]["score"]))
        return result

    def export(self, result: TournamentResult, output_dir: str | Path) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"tournament_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        return path
