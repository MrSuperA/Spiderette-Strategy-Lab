"""
量化分析引擎 — 胜率、分布、效率、置信区间、多策略对比
参考《蜘蛛纸牌移牌策略探索项目可行性研究报告》量化标准体系

设计原则：纯数据处理，不依赖 IO
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.core.session import GameResult, StepRecord
from src.core.types import Outcome


# ═══════════════════════════════════════════════════════════
#  单局详细指标
# ═══════════════════════════════════════════════════════════

@dataclass
class GameMetrics:
    """单局的详细量化指标"""
    seed: int
    outcome: str                       # "win" / "deadlock"
    total_moves: int
    total_time_ms: float
    completed: int                     # 完成序列数 (0-8)
    avg_step_ms: float                 # 平均每步耗时
    deal_count: int                    # 发牌次数
    move_count: int                    # 移牌次数（不含发牌）
    max_empty_cols: int                # 最大空列数
    avg_legal_moves: float             # 平均合法移动数
    step_times: list[float] = field(default_factory=list)  # 每步耗时序列

    @property
    def move_efficiency(self) -> float:
        """移牌效率 = 完成序列数 / 总步数"""
        return self.completed / self.total_moves if self.total_moves > 0 else 0.0

    @property
    def time_efficiency(self) -> float:
        """时间效率 = 完成序列数 / 总耗时(秒)"""
        return self.completed / (self.total_time_ms / 1000) if self.total_time_ms > 0 else 0.0

    @property
    def deal_ratio(self) -> float:
        """发牌占比 = 发牌次数 / 总步数"""
        return self.deal_count / self.total_moves if self.total_moves > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "outcome": self.outcome,
            "total_moves": self.total_moves,
            "total_time_ms": round(self.total_time_ms, 2),
            "completed": self.completed,
            "avg_step_ms": round(self.avg_step_ms, 2),
            "deal_count": self.deal_count,
            "move_count": self.move_count,
            "max_empty_cols": self.max_empty_cols,
            "avg_legal_moves": round(self.avg_legal_moves, 1),
            "move_efficiency": round(self.move_efficiency, 4),
            "deal_ratio": round(self.deal_ratio, 4),
        }


def extract_game_metrics(result: GameResult) -> GameMetrics:
    """从 GameResult 提取详细量化指标"""
    steps = result.steps
    deal_count = sum(1 for s in steps if s.move and s.move.is_deal)
    move_count = result.total_moves - deal_count

    # 每步合法移动数
    legal_counts = [s.legal_move_count for s in steps if s.legal_move_count > 0]
    avg_legal = statistics.mean(legal_counts) if legal_counts else 0.0

    # 每步耗时
    step_times = [s.elapsed_ms for s in steps]

    # 最大空列数（遍历所有状态快照）
    max_empty = 0
    for s in steps:
        cols = s.state.columns
        empty = sum(1 for c in cols if c.is_empty)
        max_empty = max(max_empty, empty)

    return GameMetrics(
        seed=result.seed,
        outcome=result.outcome.name.lower(),
        total_moves=result.total_moves,
        total_time_ms=result.total_time_ms,
        completed=result.completed,
        avg_step_ms=result.avg_step_ms,
        deal_count=deal_count,
        move_count=move_count,
        max_empty_cols=max_empty,
        avg_legal_moves=avg_legal,
        step_times=step_times,
    )


# ═══════════════════════════════════════════════════════════
#  分布统计
# ═══════════════════════════════════════════════════════════

@dataclass
class DistributionStats:
    """数值分布的统计摘要"""
    count: int = 0
    mean: float = 0.0
    std: float = 0.0
    median: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    p25: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p99: float = 0.0

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "mean": round(self.mean, 2),
            "std": round(self.std, 2),
            "median": round(self.median, 2),
            "min": round(self.min_val, 2),
            "max": round(self.max_val, 2),
            "p25": round(self.p25, 2),
            "p75": round(self.p75, 2),
            "p90": round(self.p90, 2),
            "p99": round(self.p99, 2),
        }


def compute_distribution(values: Sequence[float]) -> DistributionStats:
    """计算数值分布的统计摘要"""
    if not values:
        return DistributionStats()

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def percentile(data: list[float], p: float) -> float:
        k = (n - 1) * p / 100
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    return DistributionStats(
        count=n,
        mean=statistics.mean(sorted_vals),
        std=statistics.stdev(sorted_vals) if n > 1 else 0.0,
        median=statistics.median(sorted_vals),
        min_val=sorted_vals[0],
        max_val=sorted_vals[-1],
        p25=percentile(sorted_vals, 25),
        p75=percentile(sorted_vals, 75),
        p90=percentile(sorted_vals, 90),
        p99=percentile(sorted_vals, 99),
    )


# ═══════════════════════════════════════════════════════════
#  策略聚合统计
# ═══════════════════════════════════════════════════════════

@dataclass
class StrategyStats:
    """单策略的聚合统计 — 包含分布和效率指标"""
    name: str
    total_games: int = 0
    wins: int = 0
    deadlocks: int = 0
    total_moves: int = 0
    total_time_ms: float = 0.0
    completed_sum: int = 0
    move_counts: list[int] = field(default_factory=list)
    win_move_counts: list[int] = field(default_factory=list)
    completed_counts: list[int] = field(default_factory=list)
    step_times_all: list[float] = field(default_factory=list)
    game_metrics: list[GameMetrics] = field(default_factory=list)

    # 缓存的分布统计（在 collect_stats 后一次性计算）
    _moves_dist: Optional[DistributionStats] = field(default=None, repr=False)
    _win_moves_dist: Optional[DistributionStats] = field(default=None, repr=False)
    _completed_dist: Optional[DistributionStats] = field(default=None, repr=False)
    _step_time_dist: Optional[DistributionStats] = field(default=None, repr=False)

    # ── 基础指标 ──

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_games if self.total_games > 0 else 0.0

    @property
    def avg_moves(self) -> float:
        return self.total_moves / self.total_games if self.total_games > 0 else 0.0

    @property
    def avg_time_ms(self) -> float:
        return self.total_time_ms / self.total_games if self.total_games > 0 else 0.0

    @property
    def avg_completed(self) -> float:
        return self.completed_sum / self.total_games if self.total_games > 0 else 0.0

    # ── 置信区间 ──

    @property
    def win_rate_ci95(self) -> tuple[float, float]:
        """胜率的 95% 置信区间（Wilson score interval）"""
        if self.total_games == 0:
            return (0.0, 0.0)
        n = self.total_games
        p = self.win_rate
        z = 1.96
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
        return (max(0, center - margin), min(1, center + margin))

    # ── 分布统计（使用缓存） ──

    @property
    def moves_distribution(self) -> DistributionStats:
        if self._moves_dist is None:
            self._moves_dist = compute_distribution(self.move_counts)
        return self._moves_dist

    @property
    def win_moves_distribution(self) -> DistributionStats:
        if self._win_moves_dist is None:
            self._win_moves_dist = compute_distribution(self.win_move_counts)
        return self._win_moves_dist

    @property
    def completed_distribution(self) -> DistributionStats:
        if self._completed_dist is None:
            self._completed_dist = compute_distribution(self.completed_counts)
        return self._completed_dist

    @property
    def step_time_distribution(self) -> DistributionStats:
        if self._step_time_dist is None:
            self._step_time_dist = compute_distribution(self.step_times_all)
        return self._step_time_dist

    # ── 效率指标 ──

    @property
    def avg_move_efficiency(self) -> float:
        """平均移牌效率 = 完成序列数 / 总步数"""
        if not self.game_metrics:
            return 0.0
        return statistics.mean(m.move_efficiency for m in self.game_metrics)

    @property
    def avg_deal_ratio(self) -> float:
        """平均发牌占比"""
        if not self.game_metrics:
            return 0.0
        return statistics.mean(m.deal_ratio for m in self.game_metrics)

    @property
    def avg_max_empty_cols(self) -> float:
        """平均最大空列数"""
        if not self.game_metrics:
            return 0.0
        return statistics.mean(m.max_empty_cols for m in self.game_metrics)

    @property
    def avg_legal_moves(self) -> float:
        """平均合法移动数（局面复杂度指标）"""
        if not self.game_metrics:
            return 0.0
        return statistics.mean(m.avg_legal_moves for m in self.game_metrics)

    # ── 连胜/连败 ──

    @property
    def max_win_streak(self) -> int:
        """最长连胜"""
        streak = max_streak = 0
        for m in self.game_metrics:
            if m.outcome == "win":
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    @property
    def max_lose_streak(self) -> int:
        """最长连败"""
        streak = max_streak = 0
        for m in self.game_metrics:
            if m.outcome != "win":
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    def to_dict(self) -> dict:
        ci_lo, ci_hi = self.win_rate_ci95
        return {
            "name": self.name,
            "total_games": self.total_games,
            "wins": self.wins,
            "deadlocks": self.deadlocks,
            "win_rate": round(self.win_rate, 4),
            "win_rate_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
            "avg_moves": round(self.avg_moves, 1),
            "avg_time_ms": round(self.avg_time_ms, 1),
            "avg_completed": round(self.avg_completed, 2),
            # 分布
            "moves_dist": self.moves_distribution.to_dict(),
            "completed_dist": self.completed_distribution.to_dict(),
            "step_time_dist": self.step_time_distribution.to_dict(),
            # 效率
            "avg_move_efficiency": round(self.avg_move_efficiency, 4),
            "avg_deal_ratio": round(self.avg_deal_ratio, 4),
            "avg_max_empty_cols": round(self.avg_max_empty_cols, 1),
            "avg_legal_moves": round(self.avg_legal_moves, 1),
            # 连胜/连败
            "max_win_streak": self.max_win_streak,
            "max_lose_streak": self.max_lose_streak,
        }


# ═══════════════════════════════════════════════════════════
#  聚合函数
# ═══════════════════════════════════════════════════════════

def collect_stats(name: str, results: Sequence[GameResult]) -> StrategyStats:
    """从一组 GameResult 聚合统计 — 提取完整量化指标"""
    stats = StrategyStats(name=name)
    for r in results:
        gm = extract_game_metrics(r)
        stats.game_metrics.append(gm)

        stats.total_games += 1
        if r.outcome == Outcome.WIN:
            stats.wins += 1
            stats.win_move_counts.append(r.total_moves)
        elif r.outcome == Outcome.DEADLOCK:
            stats.deadlocks += 1
        stats.total_moves += r.total_moves
        stats.total_time_ms += r.total_time_ms
        stats.completed_sum += r.completed
        stats.move_counts.append(r.total_moves)
        stats.completed_counts.append(r.completed)
        stats.step_times_all.extend(gm.step_times)

    return stats


def compare_strategies(all_stats: Sequence[StrategyStats]) -> dict:
    """多策略对比报告 — 含排名和效率矩阵"""
    if not all_stats:
        return {}

    best_win = max(all_stats, key=lambda s: s.win_rate)
    best_eff = max(all_stats, key=lambda s: s.avg_move_efficiency)
    best_moves = min(
        (s for s in all_stats if s.wins > 0),
        key=lambda s: s.avg_moves,
        default=best_win,
    )
    fastest = min(
        (s for s in all_stats if s.wins > 0),
        key=lambda s: s.avg_time_ms,
        default=best_win,
    )

    return {
        "strategies": [s.to_dict() for s in all_stats],
        "rankings": {
            "best_win_rate": {"name": best_win.name, "rate": round(best_win.win_rate, 4)},
            "best_efficiency": {"name": best_eff.name, "efficiency": round(best_eff.avg_move_efficiency, 4)},
            "best_avg_moves": {"name": best_moves.name, "moves": round(best_moves.avg_moves, 1)},
            "fastest": {"name": fastest.name, "time_ms": round(fastest.avg_time_ms, 1)},
        },
        "total_games": sum(s.total_games for s in all_stats),
    }
