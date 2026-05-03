"""
因子分析器 — 从响应矩阵中发现策略因子
从多个策略的决策响应中提取公共因子，量化策略的"决策性格"
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.analysis.scenario import ResponseCollector, ScenarioResponse


@dataclass
class FactorResult:
    """单个因子的分析结果"""
    name: str
    display_name: str
    description: str
    strategy_scores: dict[str, float] = field(default_factory=dict)
    variance_explained: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "scores": {k: round(v, 4) for k, v in self.strategy_scores.items()},
            "variance_explained": round(self.variance_explained, 4),
        }


@dataclass
class FactorAnalysisReport:
    """因子分析报告"""
    n_strategies: int = 0
    n_scenarios: int = 0
    factors: list[FactorResult] = field(default_factory=list)
    comparison_matrix: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "n_strategies": self.n_strategies,
            "n_scenarios": self.n_scenarios,
            "factors": [f.to_dict() for f in self.factors],
            "comparison_matrix": self.comparison_matrix,
        }


# 因子定义
FACTOR_DEFINITIONS = [
    {
        "name": "suit_preservation",
        "display_name": "花色保持倾向",
        "description": "选择保持花色一致的移动的倾向",
        "feature": "preserves_suit",
    },
    {
        "name": "exposure_willingness",
        "display_name": "翻牌意愿",
        "description": "选择翻开暗牌的移动的倾向",
        "feature": "exposes_card",
    },
    {
        "name": "empty_column_usage",
        "display_name": "空列利用倾向",
        "description": "使用空列进行重组的频率",
        "feature": "uses_empty_col",
    },
    {
        "name": "deal_timing",
        "display_name": "发牌时机偏好",
        "description": "在有合法移动时选择发牌的倾向",
        "feature": "is_deal",
    },
    {
        "name": "sequence_building",
        "display_name": "序列构建倾向",
        "description": "优先移动长序列",
        "feature": "sequence_length",
        "normalize": True,  # 需要归一化到 0-1
    },
    {
        "name": "decision_speed",
        "display_name": "决策速度",
        "description": "策略做出决策的速度",
        "feature": "elapsed_ms",
        "invert": True,  # 越快越好，需要反转
    },
    {
        "name": "decision_position",
        "display_name": "选择位置偏好",
        "description": "策略倾向于选择第几个合法移动",
        "feature": "chosen_position",
    },
    {
        "name": "decision_consistency",
        "display_name": "决策一致性",
        "description": "面对相似局面时做出相同选择的程度",
        "computed": True,  # 需要特殊计算
    },
]


class FactorAnalyzer:
    """
    因子分析器

    从多个策略的响应矩阵中提取公共因子，
    量化每个策略在每个因子上的得分。
    """

    def __init__(self):
        self.report = FactorAnalysisReport()

    def analyze(
        self,
        collector: ResponseCollector,
        strategy_names: list[str],
    ) -> FactorAnalysisReport:
        """
        执行因子分析

        Args:
            collector: 已采集数据的 ResponseCollector
            strategy_names: 要分析的策略名列表

        Returns:
            FactorAnalysisReport
        """
        self.report = FactorAnalysisReport(
            n_strategies=len(strategy_names),
            n_scenarios=0,
        )

        # 获取每个策略的响应矩阵
        matrices = {}
        for name in strategy_names:
            matrix = collector.get_response_matrix(name)
            if matrix:
                matrices[name] = matrix
                self.report.n_scenarios = matrix.get("n_responses", 0)

        # 计算每个因子
        for fdef in FACTOR_DEFINITIONS:
            factor = self._compute_factor(fdef, matrices, collector, strategy_names)
            self.report.factors.append(factor)

        # 构建对比矩阵
        self.report.comparison_matrix = self._build_comparison_matrix()

        return self.report

    def _compute_factor(
        self,
        fdef: dict,
        matrices: dict,
        collector: ResponseCollector,
        strategy_names: list[str],
    ) -> FactorResult:
        """计算单个因子"""
        factor = FactorResult(
            name=fdef["name"],
            display_name=fdef["display_name"],
            description=fdef["description"],
        )

        if fdef.get("computed"):
            # 决策一致性：需要特殊计算
            for name in strategy_names:
                factor.strategy_scores[name] = self._compute_consistency(collector, name)
        else:
            feature_name = fdef["feature"]
            for name in strategy_names:
                matrix = matrices.get(name, {})
                features = matrix.get("features", {})
                feat = features.get(feature_name, {})
                score = feat.get("mean", 0)

                # 归一化
                if fdef.get("normalize") and score > 0:
                    score = min(1.0, score / 5.0)  # 序列长度归一化到 0-1

                # 反转（越快越好）
                if fdef.get("invert"):
                    score = max(0, 1.0 - min(1.0, score / 100))  # 100ms 为基准

                factor.strategy_scores[name] = score

        # 计算解释方差
        scores = list(factor.strategy_scores.values())
        if len(scores) > 1:
            var = statistics.variance(scores)
            factor.variance_explained = min(1.0, var * 4)  # 归一化

        return factor

    def _compute_consistency(self, collector: ResponseCollector, strategy_name: str) -> float:
        """计算决策一致性（基于选择位置的标准差）"""
        responses = collector.responses.get(strategy_name, [])
        if not responses:
            return 0.0

        positions = [r.chosen_move_index / max(1, r.all_moves_count) for r in responses]
        if len(positions) < 2:
            return 1.0

        std = statistics.stdev(positions)
        # 标准差越小，一致性越高
        return max(0, 1.0 - std * 2)

    def _build_comparison_matrix(self) -> dict:
        """构建策略对比矩阵"""
        matrix = {}
        for factor in self.report.factors:
            matrix[factor.name] = factor.strategy_scores
        return matrix

    def export_txt(self, output_dir: str | Path) -> Path:
        """导出文本报告"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"factor_analysis_{datetime.now():%Y%m%d_%H%M%S}.txt"

        lines = []
        lines.append("=" * 70)
        lines.append("  Spiderette Strategy Lab — 因子分析报告")
        lines.append("=" * 70)
        lines.append(f"  分析时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
        lines.append(f"  策略数量: {self.report.n_strategies}")
        lines.append(f"  场景数量: {self.report.n_scenarios}")
        lines.append("")

        # 因子得分表
        names = list(self.report.factors[0].strategy_scores.keys()) if self.report.factors else []
        header = f"  {'因子':<16} " + " ".join(f"{n:>12}" for n in names)
        lines.append(header)
        lines.append(f"  {'─'*16} " + " ".join(f"{'─'*12}" for _ in names))

        for factor in self.report.factors:
            row = f"  {factor.display_name:<14} "
            for name in names:
                score = factor.strategy_scores.get(name, 0)
                row += f"{score:>12.3f} "
            lines.append(row)

        lines.append("")

        # 每个因子的详细说明
        for factor in self.report.factors:
            lines.append(f"── {factor.display_name} ({factor.name}) ──")
            lines.append(f"  描述: {factor.description}")
            lines.append(f"  解释方差: {factor.variance_explained:.3f}")
            best = max(factor.strategy_scores.items(), key=lambda x: x[1])
            worst = min(factor.strategy_scores.items(), key=lambda x: x[1])
            lines.append(f"  最高: {best[0]} ({best[1]:.3f})  最低: {worst[0]} ({worst[1]:.3f})")
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
