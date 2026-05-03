"""
策略量化数据模板 — 描述策略本身的特征，而非牌局结果
参考《蜘蛛纸牌移牌策略探索项目可行性研究报告》的因子化描述体系

核心思想：
  牌局结果（胜率/步数）是策略的"表现"
  策略特征（偏好/决策模式/搜索行为）是策略的"本质"
  量化模板同时记录两者，支持策略间的本质对比
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════
#  一、策略身份标识
# ═══════════════════════════════════════════════════════════

@dataclass
class StrategyIdentity:
    """策略身份"""
    name: str                           # "mcts" / "greedy" / "random"
    display_name: str                   # "MCTS 标准" / "贪心策略"
    version: str = "1.0.0"
    description: str = ""
    parameters: dict = field(default_factory=dict)
    # 例: {"iterations": 200, "time_limit": 0.2, "exploration_weight": 1.41}


# ═══════════════════════════════════════════════════════════
#  二、决策特征因子（策略的"性格"）
# ═══════════════════════════════════════════════════════════

@dataclass
class DecisionFactor:
    """
    一个决策因子 — 描述策略在某维度上的倾向

    参考报告的 FactorDefinition：
    每个因子有名称、描述、得分、置信区间
    """
    name: str                           # "suit_preservation"
    display_name: str                   # "花色保持倾向"
    description: str                    # "策略选择保持花色一致的移动的倾向程度"
    low_label: str = "低"               # 低分端标签
    high_label: str = "高"              # 高分端标签
    score: float = 0.0                  # 因子得分 (0-1 归一化)
    ci_lower: float = 0.0              # 95% CI 下界
    ci_upper: float = 0.0              # 95% CI 上界
    variance_explained: float = 0.0     # 解释的方差比例

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "score": round(self.score, 4),
            "ci": [round(self.ci_lower, 4), round(self.ci_upper, 4)],
            "low_label": self.low_label,
            "high_label": self.high_label,
            "variance_explained": round(self.variance_explained, 4),
        }


# 预定义的决策因子维度
DEFAULT_FACTORS = [
    DecisionFactor(
        name="suit_preservation",
        display_name="花色保持倾向",
        description="选择保持花色一致的移动的倾向",
        low_label="花色无关", high_label="严格同花色",
    ),
    DecisionFactor(
        name="exposure_willingness",
        display_name="翻牌意愿",
        description="选择翻开暗牌的移动的倾向",
        low_label="保守", high_label="激进",
    ),
    DecisionFactor(
        name="sequence_building",
        display_name="序列构建倾向",
        description="优先构建长序列而非短期收益",
        low_label="短视", high_label="长远",
    ),
    DecisionFactor(
        name="empty_column_usage",
        display_name="空列利用倾向",
        description="使用空列进行重组的频率",
        low_label="低频", high_label="高频",
    ),
    DecisionFactor(
        name="deal_timing",
        display_name="发牌时机偏好",
        description="在还有合法移动时选择发牌的倾向",
        low_label="延迟发牌", high_label="尽早发牌",
    ),
    DecisionFactor(
        name="reversibility_preference",
        description="选择可逆移动（不翻牌、不发牌）的倾向",
        display_name="可逆性偏好",
        low_label="不关心", high_label="优先可逆",
    ),
    DecisionFactor(
        name="risk_tolerance",
        display_name="风险容忍度",
        description="选择可能破坏现有结构但潜在收益更高的移动",
        low_label="保守", high_label="冒险",
    ),
    DecisionFactor(
        name="decision_consistency",
        display_name="决策一致性",
        description="面对相似局面时做出相同选择的程度",
        low_label="随机", high_label="确定性",
    ),
]


# ═══════════════════════════════════════════════════════════
#  三、搜索行为特征（MCTS 类策略专用）
# ═══════════════════════════════════════════════════════════

@dataclass
class SearchBehavior:
    """搜索行为特征"""
    avg_iterations: float = 0.0         # 平均迭代次数
    avg_depth: float = 0.0             # 平均搜索深度
    avg_branching: float = 0.0         # 平均分支因子
    avg_time_ms: float = 0.0           # 平均搜索耗时
    exploration_weight: float = 0.0    # 探索权重
    exploitation_ratio: float = 0.0    # 利用/探索比
    tree_size_estimate: float = 0.0    # 估计搜索树大小
    cache_hit_rate: float = 0.0        # 缓存命中率

    def to_dict(self) -> dict:
        return {
            "avg_iterations": round(self.avg_iterations, 1),
            "avg_depth": round(self.avg_depth, 1),
            "avg_branching": round(self.avg_branching, 1),
            "avg_time_ms": round(self.avg_time_ms, 2),
            "exploration_weight": round(self.exploration_weight, 3),
            "exploitation_ratio": round(self.exploitation_ratio, 3),
            "tree_size_estimate": round(self.tree_size_estimate, 0),
            "cache_hit_rate": round(self.cache_hit_rate, 4),
        }


# ═══════════════════════════════════════════════════════════
#  四、表现指标（策略在牌局中的结果）
# ═══════════════════════════════════════════════════════════

@dataclass
class DistributionMetric:
    """分布统计"""
    mean: float = 0.0
    std: float = 0.0
    median: float = 0.0
    p25: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mean": round(self.mean, 2), "std": round(self.std, 2),
            "median": round(self.median, 2), "p25": round(self.p25, 2),
            "p75": round(self.p75, 2), "p90": round(self.p90, 2),
            "min": round(self.min_val, 2), "max": round(self.max_val, 2),
        }


@dataclass
class PerformanceMetrics:
    """表现指标（按难度分组）"""
    difficulty: int                     # 1 / 2 / 4
    n_games: int = 0
    wins: int = 0
    win_rate: float = 0.0
    win_rate_ci: tuple[float, float] = (0.0, 0.0)
    moves: DistributionMetric = field(default_factory=DistributionMetric)
    completed: DistributionMetric = field(default_factory=DistributionMetric)
    efficiency: DistributionMetric = field(default_factory=DistributionMetric)
    avg_step_ms: float = 0.0
    max_win_streak: int = 0
    max_lose_streak: int = 0
    deal_ratio: DistributionMetric = field(default_factory=DistributionMetric)

    def to_dict(self) -> dict:
        ci_lo, ci_hi = self.win_rate_ci
        return {
            "difficulty": self.difficulty,
            "n_games": self.n_games,
            "wins": self.wins,
            "win_rate": round(self.win_rate, 4),
            "win_rate_ci": [round(ci_lo, 4), round(ci_hi, 4)],
            "moves": self.moves.to_dict(),
            "completed": self.completed.to_dict(),
            "efficiency": self.efficiency.to_dict(),
            "avg_step_ms": round(self.avg_step_ms, 2),
            "max_win_streak": self.max_win_streak,
            "max_lose_streak": self.max_lose_streak,
            "deal_ratio": self.deal_ratio.to_dict(),
        }


# ═══════════════════════════════════════════════════════════
#  五、完整策略量化
# ═══════════════════════════════════════════════════════════

@dataclass
class StrategyQuantitativeProfile:
    """
    策略的完整量化描述 — 同时包含"本质"和"表现"

    结构：
    ┌─────────────────────────────────────┐
    │ 策略身份 (StrategyIdentity)          │
    │ ├─ 名称/版本/参数                    │
    ├─────────────────────────────────────┤
    │ 决策因子 (DecisionFactor[])          │
    │ ├─ 花色保持/翻牌意愿/序列构建/...    │
    │ ├─ 每个因子有得分 + CI               │
    ├─────────────────────────────────────┤
    │ 搜索行为 (SearchBehavior)            │
    │ ├─ 迭代/深度/分支/耗时/探索权重      │
    ├─────────────────────────────────────┤
    │ 表现指标 (PerformanceMetrics[])      │
    │ ├─ 按难度分组                        │
    │ ├─ 胜率/步数分布/完成分布/效率分布    │
    ├─────────────────────────────────────┤
    │ 测量元信息                           │
    │ ├─ 场景数/信度/引擎版本/时间戳       │
    └─────────────────────────────────────┘
    """
    identity: StrategyIdentity
    factors: list[DecisionFactor] = field(default_factory=lambda: list(DEFAULT_FACTORS))
    search_behavior: SearchBehavior = field(default_factory=SearchBehavior)
    performance: list[PerformanceMetrics] = field(default_factory=list)

    # 测量元信息
    n_scenarios_used: int = 0
    measurement_icc: float = 0.0       # 重测信度
    engine_version: str = "1.0.0"
    measured_at: str = ""

    def to_dict(self) -> dict:
        return {
            "identity": {
                "name": self.identity.name,
                "display_name": self.identity.display_name,
                "version": self.identity.version,
                "description": self.identity.description,
                "parameters": self.identity.parameters,
            },
            "factors": [f.to_dict() for f in self.factors],
            "search_behavior": self.search_behavior.to_dict(),
            "performance": [p.to_dict() for p in self.performance],
            "measurement": {
                "n_scenarios": self.n_scenarios_used,
                "icc": round(self.measurement_icc, 3),
                "engine_version": self.engine_version,
                "measured_at": self.measured_at or datetime.now().isoformat(),
            },
        }

    def to_compact_dict(self) -> dict:
        """紧凑格式（用于快速对比）"""
        return {
            "name": self.identity.name,
            "factors": {f.name: round(f.score, 3) for f in self.factors},
            "win_rates": {str(p.difficulty): round(p.win_rate, 4) for p in self.performance},
            "avg_efficiency": {
                str(p.difficulty): round(
                    p.efficiency.mean if p.efficiency else 0, 4
                ) for p in self.performance
            },
        }


# ═══════════════════════════════════════════════════════════
#  六、多策略对比矩阵
# ═══════════════════════════════════════════════════════════

@dataclass
class StrategyComparisonMatrix:
    """多策略对比矩阵"""
    profiles: list[StrategyQuantitativeProfile] = field(default_factory=list)
    comparison_dimensions: list[str] = field(default_factory=lambda: [
        "win_rate", "avg_moves", "avg_completed", "avg_efficiency",
        "suit_preservation", "exposure_willingness", "sequence_building",
        "decision_consistency",
    ])

    def to_dict(self) -> dict:
        matrix = {}
        for dim in self.comparison_dimensions:
            matrix[dim] = {}
            for p in self.profiles:
                name = p.identity.name
                if dim == "win_rate":
                    matrix[dim][name] = {
                        str(perf.difficulty): round(perf.win_rate, 4)
                        for perf in p.performance
                    }
                elif dim in {f.name for f in p.factors}:
                    factor = next((f for f in p.factors if f.name == dim), None)
                    matrix[dim][name] = round(factor.score, 3) if factor else 0
                elif dim == "avg_moves":
                    matrix[dim][name] = {
                        str(perf.difficulty): round(perf.moves.mean, 1)
                        for perf in p.performance
                    }
                elif dim == "avg_completed":
                    matrix[dim][name] = {
                        str(perf.difficulty): round(perf.completed.mean, 2)
                        for perf in p.performance
                    }
                elif dim == "avg_efficiency":
                    matrix[dim][name] = {
                        str(perf.difficulty): round(perf.efficiency.mean, 4)
                        for perf in p.performance
                    }

        return {
            "dimensions": self.comparison_dimensions,
            "strategies": [p.identity.name for p in self.profiles],
            "matrix": matrix,
            "profiles": [p.to_compact_dict() for p in self.profiles],
        }


# ═══════════════════════════════════════════════════════════
#  七、导出器
# ═══════════════════════════════════════════════════════════

class StrategyProfileExporter:
    """策略量化导出器"""

    def __init__(self):
        self._profiles: list[StrategyQuantitativeProfile] = []

    def add_profile(self, profile: StrategyQuantitativeProfile) -> None:
        self._profiles.append(profile)

    def export_json(self, output_dir: str | Path) -> Path:
        """导出 JSON"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        comparison = StrategyComparisonMatrix(profiles=self._profiles)
        data = {
            "export_time": datetime.now().isoformat(),
            "n_strategies": len(self._profiles),
            "profiles": [p.to_dict() for p in self._profiles],
            "comparison": comparison.to_dict(),
        }
        path = out / f"strategy_profile_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def export_txt(self, output_dir: str | Path) -> Path:
        """导出可读文本报告"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"strategy_profile_{datetime.now():%Y%m%d_%H%M%S}.txt"
        lines = []
        lines.append("=" * 70)
        lines.append("  Spiderette Strategy Lab — 策略量化")
        lines.append("=" * 70)
        lines.append(f"  导出时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
        lines.append(f"  策略数量: {len(self._profiles)}")
        lines.append("")

        for p in self._profiles:
            lines.append(f"── {p.identity.display_name} ({p.identity.name} v{p.identity.version}) {'─'*30}")
            if p.identity.description:
                lines.append(f"  描述: {p.identity.description}")
            if p.identity.parameters:
                params = ', '.join(f'{k}={v}' for k, v in p.identity.parameters.items())
                lines.append(f"  参数: {params}")
            lines.append("")

            # 决策因子
            lines.append("  决策因子:")
            lines.append(f"    {'因子':<16} {'得分':>6} {'95% CI':>14} {'描述'}")
            lines.append(f"    {'─'*16} {'─'*6} {'─'*14} {'─'*20}")
            for f in p.factors:
                ci = f"[{f.ci_lower:.3f}, {f.ci_upper:.3f}]"
                bar = "█" * int(f.score * 10) + "░" * (10 - int(f.score * 10))
                lines.append(f"    {f.display_name:<14} {f.score:>6.3f} {ci:>14} {bar} {f.low_label}←→{f.high_label}")
            lines.append("")

            # 搜索行为
            sb = p.search_behavior
            if sb.avg_iterations > 0:
                lines.append("  搜索行为:")
                lines.append(f"    平均迭代: {sb.avg_iterations:.0f}  平均深度: {sb.avg_depth:.1f}  平均分支: {sb.avg_branching:.1f}")
                lines.append(f"    平均耗时: {sb.avg_time_ms:.1f}ms  探索权重: {sb.exploration_weight:.3f}  缓存命中: {sb.cache_hit_rate:.1%}")
                lines.append("")

            # 表现指标
            for perf in p.performance:
                ci_lo, ci_hi = perf.win_rate_ci
                lines.append(f"  表现 ({perf.difficulty}花色, {perf.n_games}局):")
                lines.append(f"    胜率: {perf.win_rate:.1%} [{ci_lo:.1%}, {ci_hi:.1%}]")
                lines.append(f"    步数: 均值={perf.moves.mean:.0f} 标准差={perf.moves.std:.1f} 中位数={perf.moves.median:.0f} P90={perf.moves.p90:.0f}")
                lines.append(f"    完成: 均值={perf.completed.mean:.1f}/8 标准差={perf.completed.std:.1f}")
                lines.append(f"    效率: 均值={perf.efficiency.mean:.4f} 标准差={perf.efficiency.std:.4f}")
                lines.append(f"    步均耗时: {perf.avg_step_ms:.1f}ms  连胜: {perf.max_win_streak}  连败: {perf.max_lose_streak}")
                lines.append("")

            # 测量信息
            lines.append(f"  测量: {p.n_scenarios_used}场景  信度ICC={p.measurement_icc:.3f}  引擎v{p.engine_version}")
            lines.append("")

        # 对比矩阵
        if len(self._profiles) > 1:
            comparison = StrategyComparisonMatrix(profiles=self._profiles)
            lines.append("── 策略对比矩阵 ──" + "─" * 50)
            lines.append("")
            names = [p.identity.name for p in self._profiles]
            header = f"    {'维度':<16} " + " ".join(f"{n:>12}" for n in names)
            lines.append(header)
            lines.append(f"    {'─'*16} " + " ".join(f"{'─'*12}" for _ in names))
            for dim in comparison.comparison_dimensions:
                row = f"    {dim:<16} "
                for p in self._profiles:
                    if dim == "win_rate":
                        val = p.performance[0].win_rate if p.performance else 0
                        row += f"{val:>11.1%} "
                    elif dim in {f.name for f in p.factors}:
                        f = next((f for f in p.factors if f.name == dim), None)
                        row += f"{f.score:>12.3f} " if f else f"{'N/A':>12} "
                    elif dim == "avg_moves":
                        val = p.performance[0].moves.mean if p.performance else 0
                        row += f"{val:>12.0f} "
                    elif dim == "avg_completed":
                        val = p.performance[0].completed.mean if p.performance else 0
                        row += f"{val:>12.2f} "
                    elif dim == "avg_efficiency":
                        val = p.performance[0].efficiency.mean if p.performance else 0
                        row += f"{val:>12.4f} "
                    else:
                        row += f"{'N/A':>12} "
                lines.append(row)
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
