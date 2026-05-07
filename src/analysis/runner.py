"""
实验运行器 — 配置驱动、结果可复现
支持 TOML 配置文件定义实验，自动运行并输出报告

新增 BenchmarkRunner：参考《蜘蛛纸牌移牌策略探索项目可行性研究报告》
"""

from __future__ import annotations

import json
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from src.core.session import GameResult, GameSession
from src.core.types import GameState, Strategy
from src.core.rules import RulesEngine
from src.envs.simulator import SimulatorEnv
from src.analysis.metrics import StrategyStats, collect_stats, compare_strategies
from src.analysis.report import ReportGenerator
from src.analysis.utils import run_single_game


@dataclass
class ExperimentConfig:
    """实验配置"""
    name: str = "unnamed"
    description: str = ""
    difficulty: int = 2
    seeds: list[int] = field(default_factory=lambda: list(range(1, 101)))
    max_moves: int = 500
    strategies: list[dict] = field(default_factory=list)


class ExperimentRunner:
    """
    配置驱动的实验运行器

    用法::

        runner = ExperimentRunner()
        result = runner.run_from_config("experiments/test.toml")
        result = runner.run(strategy, difficulty=2, seeds=[1..100])
    """

    def __init__(self, on_progress: Optional[callable] = None):
        self._on_progress = on_progress
        self._running = False

    def run(
        self,
        strategies: dict[str, Strategy],
        *,
        difficulty: int = 2,
        seeds: Sequence[int] = (1,),
        max_moves: int = 500,
        output_dir: Optional[str] = None,
        experiment_name: str = "",
    ) -> dict:
        """
        运行实验：同一组牌局，每个策略各跑一遍

        Returns:
            {strategies: [...], total_games: N, output_dir: "..."}
        """
        self._running = True
        all_stats: list[StrategyStats] = []
        total = len(strategies) * len(seeds)
        done = 0

        for strat_name, strategy in strategies.items():
            results: list[GameResult] = []
            for seed in seeds:
                if not self._running:
                    break

                result = run_single_game(seed, difficulty, strategy, max_moves)
                results.append(result)

                done += 1
                if self._on_progress:
                    self._on_progress({
                        "phase": "running",
                        "strategy": strat_name,
                        "seed": seed,
                        "done": done,
                        "total": total,
                        "outcome": result.outcome.name.lower(),
                    })

            stats = collect_stats(strat_name, results)
            all_stats.append(stats)

        # 生成报告
        comparison = compare_strategies(all_stats)
        if output_dir:
            reporter = ReportGenerator(all_stats, experiment_name)
            reporter.export(output_dir, formats=["json", "csv", "markdown"])
            self._save_details(all_stats, output_dir)

        return comparison

    def run_from_config(self, config_path: str) -> dict:
        """从 TOML 配置文件运行实验"""
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)

        exp = cfg.get("experiment", {})
        game = cfg.get("game", {})
        output = cfg.get("output", {})

        strategies = {}
        for s_cfg in cfg.get("strategies", []):
            strat = self._build_strategy(s_cfg)
            strategies[s_cfg["name"]] = strat

        seeds = self._parse_seeds(game.get("seeds", [1]))

        return self.run(
            strategies=strategies,
            difficulty=game.get("difficulty", 2),
            seeds=seeds,
            max_moves=game.get("max_moves", 500),
            output_dir=output.get("dir"),
            experiment_name=exp.get("name", ""),
        )

    def stop(self) -> None:
        self._running = False

    # ── 内部方法 ──

    def _build_strategy(self, cfg: dict) -> Strategy:
        """从配置构建策略实例（通过注册中心）"""
        from src.strategy.registry import get_strategy

        stype = cfg.get("type", "mcts")
        params = cfg.get("params", {})
        return get_strategy(stype, **params)

    def _parse_seeds(self, seeds) -> list[int]:
        if isinstance(seeds, list):
            return seeds
        if isinstance(seeds, str):
            if seeds.startswith("range("):
                parts = seeds[6:-1].split(",")
                return list(range(int(parts[0]), int(parts[1])))
        return [1]

    def _save_details(self, all_stats: list[StrategyStats], output_dir: str) -> None:
        """保存详细统计数据"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        details = {s.name: s.to_dict() for s in all_stats}
        with open(out / "details.json", "w", encoding="utf-8") as f:
            json.dump(details, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════
#  BenchmarkRunner — 基准测试框架
#  参考《蜘蛛纸牌移牌策略探索项目可行性研究报告》
# ═══════════════════════════════════════════════════════════

class BenchmarkRunner:
    """
    策略基准测试框架 — 标准化评估策略性能

    参考报告第 2.2 节 StrategyBenchmark 设计：
    - 统一牌局种子，公平对比
    - 多难度梯度测试
    - 完整量化指标输出
    - 自动报告生成

    用法::

        runner = BenchmarkRunner()
        result = runner.run(
            strategies={"greedy": GreedyStrategy(), "mcts": create_mcts()},
            difficulties=[1, 2],
            num_games=100,
        )
        runner.print_summary()
        runner.export("benchmark_results")
    """

    def __init__(self, on_progress: Optional[callable] = None):
        self._on_progress = on_progress
        self._results: dict[str, dict] = {}  # key: "strategy|difficulty"
        self._all_stats: list[StrategyStats] = []

    def run(
        self,
        strategies: dict[str, Strategy],
        *,
        difficulties: Sequence[int] = (1,),
        num_games: int = 100,
        seeds: Optional[Sequence[int]] = None,
        max_moves: int = 500,
    ) -> dict:
        """
        运行基准测试

        Args:
            strategies: {名称: 策略实例}
            difficulties: 难度列表 [1, 2, 4]
            num_games: 每个难度的测试局数
            seeds: 自定义种子列表（默认 range(1, num_games+1)）
            max_moves: 每局最大步数

        Returns:
            完整的基准测试结果
        """
        if seeds is None:
            seeds = list(range(1, num_games + 1))

        self._all_stats = []
        self._results = {}
        total_tasks = len(strategies) * len(difficulties) * len(seeds)
        done = 0

        for difficulty in difficulties:
            for strat_name, strategy in strategies.items():
                results: list[GameResult] = []
                t0 = time.perf_counter()

                for seed in seeds:
                    result = run_single_game(seed, difficulty, strategy, max_moves)
                    results.append(result)

                    done += 1
                    if self._on_progress:
                        self._on_progress({
                            "strategy": strat_name,
                            "difficulty": difficulty,
                            "seed": seed,
                            "done": done,
                            "total": total_tasks,
                            "outcome": result.outcome.name.lower(),
                        })

                elapsed = time.perf_counter() - t0
                stats = collect_stats(strat_name, results)
                self._all_stats.append(stats)

                key = f"{strat_name}|{difficulty}"
                self._results[key] = {
                    "strategy": strat_name,
                    "difficulty": difficulty,
                    "stats": stats,
                    "wall_time_s": round(elapsed, 2),
                }

        return self._build_report()

    def _build_report(self) -> dict:
        """构建完整基准报告"""
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "benchmarks": [],
            "comparison": compare_strategies(self._all_stats),
        }

        for key, entry in self._results.items():
            stats: StrategyStats = entry["stats"]
            report["benchmarks"].append({
                "strategy": entry["strategy"],
                "difficulty": entry["difficulty"],
                "wall_time_s": entry["wall_time_s"],
                **stats.to_dict(),
            })

        return report

    def print_summary(self) -> str:
        """生成可打印的文本摘要"""
        lines = []
        lines.append("=" * 70)
        lines.append("  蜘蛛纸牌策略基准测试报告")
        lines.append("=" * 70)
        lines.append(f"  生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 按难度分组
        difficulties = sorted(set(e["difficulty"] for e in self._results.values()))
        for diff in difficulties:
            lines.append(f"── {diff} 花色 {'─' * 50}")
            lines.append("")
            lines.append(
                f"  {'策略':<12} {'胜率':>8} {'95% CI':>16} "
                f"{'均步数':>8} {'均完成':>8} {'效率':>8} {'耗时':>8}"
            )
            lines.append(f"  {'─' * 12} {'─' * 8} {'─' * 16} {'─' * 8} {'─' * 8} {'─' * 8} {'─' * 8}")

            for key, entry in self._results.items():
                if entry["difficulty"] != diff:
                    continue
                s: StrategyStats = entry["stats"]
                ci_lo, ci_hi = s.win_rate_ci95
                lines.append(
                    f"  {s.name:<12} {s.win_rate:>7.1%} "
                    f"[{ci_lo:>5.1%}, {ci_hi:>5.1%}] "
                    f"{s.avg_moves:>7.0f} {s.avg_completed:>7.1f} "
                    f"{s.avg_move_efficiency:>7.4f} {entry['wall_time_s']:>7.1f}s"
                )
            lines.append("")

        # 排名
        comp = compare_strategies(self._all_stats)
        rankings = comp.get("rankings", {})
        lines.append("── 排名 ──────────────────────────────────────")
        for metric, info in rankings.items():
            label = {
                "best_win_rate": "最高胜率",
                "best_efficiency": "最高效率",
                "best_avg_moves": "最少步数",
                "fastest": "最快速度",
            }.get(metric, metric)
            lines.append(f"  {label}: {info['name']}")
        lines.append("")
        lines.append("=" * 70)

        return "\n".join(lines)

    def export(self, output_dir: str) -> Path:
        """导出完整报告到目录"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON 报告
        report = self._build_report()
        with open(out / "benchmark_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # 文本摘要
        summary = self.print_summary()
        with open(out / "benchmark_summary.txt", "w", encoding="utf-8") as f:
            f.write(summary)

        # CSV 明细
        import csv
        with open(out / "benchmark_results.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "strategy", "difficulty", "games", "wins", "deadlocks",
                "win_rate", "ci95_lo", "ci95_hi",
                "avg_moves", "avg_time_ms", "avg_completed",
                "move_efficiency", "deal_ratio", "avg_legal_moves",
                "max_win_streak", "max_lose_streak", "wall_time_s",
            ])
            for key, entry in self._results.items():
                s: StrategyStats = entry["stats"]
                ci_lo, ci_hi = s.win_rate_ci95
                writer.writerow([
                    entry["strategy"], entry["difficulty"],
                    s.total_games, s.wins, s.deadlocks,
                    f"{s.win_rate:.4f}", f"{ci_lo:.4f}", f"{ci_hi:.4f}",
                    f"{s.avg_moves:.1f}", f"{s.avg_time_ms:.1f}",
                    f"{s.avg_completed:.2f}",
                    f"{s.avg_move_efficiency:.4f}", f"{s.avg_deal_ratio:.4f}",
                    f"{s.avg_legal_moves:.1f}",
                    s.max_win_streak, s.max_lose_streak,
                    entry["wall_time_s"],
                ])

        # Markdown 报告
        Reporter = ReportGenerator
        reporter = Reporter(self._all_stats, "基准测试")
        reporter.export(out, formats=["markdown"])

        return out
