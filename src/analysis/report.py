"""
报告生成器 — CSV / JSON / Markdown / 文本摘要
参考《蜘蛛纸牌移牌策略探索项目可行性研究报告》报告格式
设计原则：纯 IO，不依赖策略逻辑
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Sequence

from src.analysis.metrics import StrategyStats, compare_strategies


class ReportGenerator:
    """多格式实验报告导出"""

    def __init__(self, stats: Sequence[StrategyStats], experiment_name: str = ""):
        self.stats = list(stats)
        self.name = experiment_name or f"experiment_{datetime.now():%Y%m%d_%H%M%S}"

    def export(self, output_dir: str | Path, formats: Sequence[str] = ("json",)) -> Path:
        """导出报告到指定目录"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        for fmt in formats:
            if fmt == "json":
                self._export_json(out)
            elif fmt == "csv":
                self._export_csv(out)
            elif fmt == "markdown":
                self._export_markdown(out)
            elif fmt == "text":
                self._export_text(out)

        return out

    def _export_json(self, out: Path) -> None:
        data = {
            "experiment": self.name,
            "timestamp": datetime.now().isoformat(),
            "comparison": compare_strategies(self.stats),
            "per_strategy": {s.name: s.to_dict() for s in self.stats},
        }
        path = out / "report.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _export_csv(self, out: Path) -> None:
        path = out / "report.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "strategy", "games", "wins", "deadlocks",
                "win_rate", "ci95_lo", "ci95_hi",
                "avg_moves", "avg_time_ms", "avg_completed",
                "move_efficiency", "deal_ratio", "avg_legal_moves",
                "max_win_streak", "max_lose_streak",
                "moves_std", "moves_median", "moves_p90",
            ])
            for s in self.stats:
                ci_lo, ci_hi = s.win_rate_ci95
                md = s.moves_distribution
                writer.writerow([
                    s.name, s.total_games, s.wins, s.deadlocks,
                    f"{s.win_rate:.4f}", f"{ci_lo:.4f}", f"{ci_hi:.4f}",
                    f"{s.avg_moves:.1f}", f"{s.avg_time_ms:.1f}", f"{s.avg_completed:.2f}",
                    f"{s.avg_move_efficiency:.4f}", f"{s.avg_deal_ratio:.4f}",
                    f"{s.avg_legal_moves:.1f}",
                    s.max_win_streak, s.max_lose_streak,
                    f"{md.std:.1f}", f"{md.median:.1f}", f"{md.p90:.1f}",
                ])

    def _export_markdown(self, out: Path) -> None:
        path = out / "report.md"
        lines = [
            f"# {self.name}",
            "",
            f"生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
            "",
            "## 策略对比总览",
            "",
            "| 策略 | 局数 | 胜率 | 95% CI | 平均步数 | 平均耗时 | 平均完成 |",
            "|------|------|------|--------|---------|---------|---------|",
        ]
        for s in self.stats:
            ci_lo, ci_hi = s.win_rate_ci95
            lines.append(
                f"| {s.name} | {s.total_games} | {s.win_rate:.1%} "
                f"| [{ci_lo:.1%}, {ci_hi:.1%}] "
                f"| {s.avg_moves:.0f} | {s.avg_time_ms:.0f}ms "
                f"| {s.avg_completed:.1f}/8 |"
            )

        # 效率指标
        lines.extend([
            "",
            "## 效率指标",
            "",
            "| 策略 | 移牌效率 | 发牌占比 | 平均合法移动 | 最大空列 | 连胜 | 连败 |",
            "|------|---------|---------|------------|---------|------|------|",
        ])
        for s in self.stats:
            lines.append(
                f"| {s.name} | {s.avg_move_efficiency:.4f} "
                f"| {s.avg_deal_ratio:.1%} "
                f"| {s.avg_legal_moves:.1f} "
                f"| {s.avg_max_empty_cols:.1f} "
                f"| {s.max_win_streak} | {s.max_lose_streak} |"
            )

        # 分布统计
        lines.extend([
            "",
            "## 步数分布",
            "",
            "| 策略 | 均值 | 标准差 | 中位数 | P25 | P75 | P90 | 最小 | 最大 |",
            "|------|------|--------|--------|-----|-----|-----|------|------|",
        ])
        for s in self.stats:
            md = s.moves_distribution
            lines.append(
                f"| {s.name} | {md.mean:.0f} | {md.std:.0f} "
                f"| {md.median:.0f} | {md.p25:.0f} | {md.p75:.0f} "
                f"| {md.p90:.0f} | {md.min_val:.0f} | {md.max_val:.0f} |"
            )

        # 结论
        if self.stats:
            comp = compare_strategies(self.stats)
            rankings = comp.get("rankings", {})
            lines.extend(["", "## 结论", ""])
            for metric, info in rankings.items():
                label = {
                    "best_win_rate": "最高胜率",
                    "best_efficiency": "最高效率",
                    "best_avg_moves": "最少步数",
                    "fastest": "最快速度",
                }.get(metric, metric)
                lines.append(f"- **{label}**: {info['name']}")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _export_text(self, out: Path) -> None:
        """导出纯文本摘要（适合终端显示）"""
        path = out / "summary.txt"
        lines = []
        lines.append("=" * 60)
        lines.append(f"  {self.name}")
        lines.append("=" * 60)
        lines.append(f"  时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
        lines.append("")

        lines.append(
            f"  {'策略':<10} {'胜率':>8} {'均步数':>8} "
            f"{'均完成':>8} {'效率':>8} {'连败':>6}"
        )
        lines.append(f"  {'─' * 10} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 6}")

        for s in self.stats:
            lines.append(
                f"  {s.name:<10} {s.win_rate:>7.1%} {s.avg_moves:>7.0f} "
                f"{s.avg_completed:>7.1f} {s.avg_move_efficiency:>7.4f} "
                f"{s.max_lose_streak:>5}"
            )

        lines.append("")
        lines.append("=" * 60)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
