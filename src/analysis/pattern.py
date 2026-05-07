"""
模式挖掘 — 从历史数据中发现致胜模式和死局前兆
基于 exporter 收集的数据进行统计分析
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PatternResult:
    """挖掘结果"""
    pattern_type: str       # "winning_opening" / "deadlock_signal" / "common_sequence"
    description: str
    confidence: float       # 0-1
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.pattern_type, "description": self.description,
                "confidence": round(self.confidence, 3), "data": self.data}


@dataclass
class MiningReport:
    """挖掘报告"""
    n_games: int = 0
    patterns: list[PatternResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"n_games": self.n_games, "patterns": [p.to_dict() for p in self.patterns],
                "recommendations": self.recommendations}


class PatternMiner:
    """
    模式挖掘器

    从 GameExportData 列表中挖掘：
    1. 胜利局的开局特征
    2. 死局前的共同信号
    3. 高频移动模式
    """

    def mine(self, games: list[dict]) -> MiningReport:
        """挖掘模式"""
        report = MiningReport(n_games=len(games))
        wins = [g for g in games if g.get("outcome") == "win"]
        losses = [g for g in games if g.get("outcome") == "deadlock"]

        if wins:
            report.patterns.extend(self._analyze_openings(wins, "winning"))
        if losses:
            report.patterns.extend(self._analyze_openings(losses, "losing"))
            report.patterns.extend(self._analyze_deadlock_signals(losses))
        if wins and losses:
            report.patterns.extend(self._compare_win_loss(wins, losses))

        report.recommendations = self._generate_recommendations(report.patterns)
        return report

    def _analyze_openings(self, games: list[dict], label: str) -> list[PatternResult]:
        """分析开局特征"""
        patterns = []
        empty_cols = []
        stock_remaining = []
        completed = []

        for g in games:
            steps = g.get("steps", [])
            if steps:
                empty_cols.append(steps[0].get("empty_cols", 0))
                stock_remaining.append(steps[0].get("stock_remaining", 0))
                completed.append(steps[0].get("completed", 0))

        if empty_cols:
            avg_empty = statistics.mean(empty_cols)
            patterns.append(PatternResult(
                pattern_type=f"{label}_opening_empty_cols",
                description=f"{'胜利' if label=='winning' else '失败'}局平均开局空列数",
                confidence=0.8,
                data={"mean": round(avg_empty, 2), "std": round(statistics.stdev(empty_cols), 2) if len(empty_cols) > 1 else 0}
            ))

        return patterns

    def _analyze_deadlock_signals(self, losses: list[dict]) -> list[PatternResult]:
        """分析死局前兆"""
        patterns = []
        pre_deadlock_empty = []
        pre_deadlock_stock = []
        pre_deadlock_completed = []

        for g in losses:
            steps = g.get("steps", [])
            if len(steps) >= 5:
                last5 = steps[-5:]
                pre_deadlock_empty.append(statistics.mean(s.get("empty_cols", 0) for s in last5))
                pre_deadlock_stock.append(last5[-1].get("stock_remaining", 0))
                pre_deadlock_completed.append(last5[-1].get("completed", 0))

        if pre_deadlock_empty:
            patterns.append(PatternResult(
                pattern_type="deadlock_signal_empty_cols",
                description="死局前5步平均空列数",
                confidence=0.7,
                data={"mean": round(statistics.mean(pre_deadlock_empty), 2)}
            ))
            patterns.append(PatternResult(
                pattern_type="deadlock_signal_stock",
                description="死局时剩余发牌数",
                confidence=0.9,
                data={"mean": round(statistics.mean(pre_deadlock_stock), 2),
                      "zero_ratio": round(sum(1 for s in pre_deadlock_stock if s == 0) / len(pre_deadlock_stock), 2)}
            ))
            patterns.append(PatternResult(
                pattern_type="deadlock_signal_completed",
                description="死局时完成序列数",
                confidence=0.9,
                data={"mean": round(statistics.mean(pre_deadlock_completed), 2)}
            ))

        return patterns

    def _compare_win_loss(self, wins: list[dict], losses: list[dict]) -> list[PatternResult]:
        """对比胜利局和失败局的差异"""
        patterns = []

        win_steps = [len(g.get("steps", [])) for g in wins]
        loss_steps = [len(g.get("steps", [])) for g in losses]

        if win_steps and loss_steps:
            patterns.append(PatternResult(
                pattern_type="step_count_difference",
                description="胜利局vs失败局平均步数差异",
                confidence=0.8,
                data={"win_mean": round(statistics.mean(win_steps), 0),
                      "loss_mean": round(statistics.mean(loss_steps), 0)}
            ))

        win_deals = [sum(1 for s in g.get("steps", []) if s.get("action") == "deal") for g in wins]
        loss_deals = [sum(1 for s in g.get("steps", []) if s.get("action") == "deal") for g in losses]

        if win_deals and loss_deals:
            patterns.append(PatternResult(
                pattern_type="deal_count_difference",
                description="胜利局vs失败局平均发牌次数差异",
                confidence=0.7,
                data={"win_mean": round(statistics.mean(win_deals), 1),
                      "loss_mean": round(statistics.mean(loss_deals), 1)}
            ))

        return patterns

    def _generate_recommendations(self, patterns: list[PatternResult]) -> list[str]:
        """根据挖掘结果生成建议"""
        recs = []
        for p in patterns:
            if "deadlock_signal_stock" in p.pattern_type:
                if p.data.get("zero_ratio", 0) > 0.7:
                    recs.append("超过70%的死局发生在发牌用尽后，建议优化发牌时机")
            if "deadlock_signal_empty_cols" in p.pattern_type:
                if p.data.get("mean", 0) < 0.5:
                    recs.append("死局时空列数偏低，建议增加空列利用策略")
            if "deal_count_difference" in p.pattern_type:
                if p.data.get("win_mean", 0) < p.data.get("loss_mean", 0):
                    recs.append("胜利局发牌次数更少，建议延迟发牌时机")
        return recs

    def export(self, report: MiningReport, output_dir: str | Path) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"patterns_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        return path
