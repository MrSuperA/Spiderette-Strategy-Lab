"""
分析层扩展测试 — 覆盖 compare、exporter、genetic、tournament、utils
"""

import pytest
import json
from pathlib import Path
from src.core.rules import RulesEngine
from src.core.session import GameResult, GameSession
from src.core.types import Outcome
from src.envs.generator import generate_game
from src.envs.simulator import SimulatorEnv
from src.strategy.compose import GreedyStrategy, RandomStrategy
from src.analysis.metrics import collect_stats, compare_strategies, compute_distribution, DistributionStats
from src.analysis.utils import run_single_game, run_games_batch


@pytest.fixture
def rules():
    return RulesEngine()


@pytest.fixture
def greedy():
    return GreedyStrategy()


@pytest.fixture
def random_strategy():
    return RandomStrategy()


# ═══════════════════════════════════════════════════
#  utils.py 测试
# ═══════════════════════════════════════════════════

class TestUtils:
    """公共工具函数"""

    def test_run_single_game_returns_result(self, greedy):
        result = run_single_game(seed=1, difficulty=1, strategy=greedy, max_moves=100)
        assert isinstance(result, GameResult)
        assert result.total_moves > 0

    def test_run_single_game_deterministic(self, greedy):
        """同 seed 应产生相同结果"""
        r1 = run_single_game(seed=42, difficulty=1, strategy=greedy, max_moves=200)
        r2 = run_single_game(seed=42, difficulty=1, strategy=greedy, max_moves=200)
        assert r1.outcome == r2.outcome
        assert r1.total_moves == r2.total_moves

    def test_run_games_batch(self, greedy):
        results = run_games_batch(greedy, seeds=[1, 2, 3], difficulty=1, max_moves=100)
        assert len(results) == 3
        assert all(isinstance(r, GameResult) for r in results)

    def test_run_games_batch_with_progress(self, greedy):
        progress_calls = []
        results = run_games_batch(
            greedy, seeds=[1, 2], difficulty=1, max_moves=100,
            on_progress=lambda p: progress_calls.append(p),
            strategy_name="greedy",
        )
        assert len(progress_calls) == 2
        assert progress_calls[0]["done"] == 1
        assert progress_calls[1]["done"] == 2


# ═══════════════════════════════════════════════════
#  metrics.py 扩展测试
# ═══════════════════════════════════════════════════

class TestMetricsExtended:
    """量化指标引擎扩展测试"""

    def test_win_rate_ci95_with_zero_games(self):
        stats = collect_stats("test", [])
        assert stats.win_rate_ci95 == (0.0, 0.0)

    def test_win_rate_ci95_bounds(self, greedy):
        """置信区间应在 [0, 1] 内"""
        results = run_games_batch(greedy, seeds=list(range(1, 11)), difficulty=1, max_moves=200)
        stats = collect_stats("greedy", results)
        ci_lo, ci_hi = stats.win_rate_ci95
        assert 0.0 <= ci_lo <= ci_hi <= 1.0

    def test_distribution_caching(self, greedy):
        """分布属性应被缓存（多次访问返回同一对象）"""
        results = run_games_batch(greedy, seeds=[1, 2, 3], difficulty=1, max_moves=100)
        stats = collect_stats("greedy", results)
        d1 = stats.moves_distribution
        d2 = stats.moves_distribution
        assert d1 is d2

    def test_compute_distribution_empty(self):
        d = compute_distribution([])
        assert d.count == 0
        assert d.mean == 0.0

    def test_compute_distribution_single(self):
        d = compute_distribution([5.0])
        assert d.count == 1
        assert d.mean == 5.0
        assert d.std == 0.0

    def test_compare_strategies_empty(self):
        result = compare_strategies([])
        assert result == {}

    def test_streak_properties(self, greedy):
        results = run_games_batch(greedy, seeds=list(range(1, 6)), difficulty=1, max_moves=200)
        stats = collect_stats("greedy", results)
        assert stats.max_win_streak >= 0
        assert stats.max_lose_streak >= 0
        assert stats.max_win_streak + stats.max_lose_streak <= stats.total_games


# ═══════════════════════════════════════════════════
#  compare.py 测试
# ═══════════════════════════════════════════════════

class TestCompare:
    """多策略对比"""

    def test_comparison_report_structure(self):
        from src.analysis.compare import ParallelStrategyRunner
        runner = ParallelStrategyRunner()
        report = runner.compare(
            strategy_names=["greedy", "random"],
            difficulty=1,
            seeds=[1, 2, 3],
            max_moves=100,
            parallel=False,
        )
        assert len(report.comparisons) == 3
        assert "greedy" in report.stats
        assert "random" in report.stats

    def test_comparison_to_dict(self):
        from src.analysis.compare import ParallelStrategyRunner
        runner = ParallelStrategyRunner()
        report = runner.compare(
            strategy_names=["greedy"],
            difficulty=1,
            seeds=[1],
            max_moves=100,
            parallel=False,
        )
        d = report.to_dict()
        assert "strategies" in d
        assert "rankings" in d


# ═══════════════════════════════════════════════════
#  exporter.py 测试
# ═══════════════════════════════════════════════════

class TestExporter:
    """牌局导出"""

    def test_export_json(self, greedy, tmp_path):
        from src.analysis.exporter import GameExporter
        exporter = GameExporter()
        exporter.start_game(seed=1, difficulty=1, strategy="greedy")
        exporter.record_step(step=1, action="move", src_col=0, dst_col=1)
        exporter.end_game(outcome="win", total_moves=1, total_time_ms=100.0, completed=8)
        path = exporter.export_json(tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["total_games"] == 1

    def test_export_csv(self, greedy, tmp_path):
        from src.analysis.exporter import GameExporter
        exporter = GameExporter()
        exporter.start_game(seed=1, difficulty=1, strategy="greedy")
        exporter.record_step(step=1, action="move")
        exporter.end_game(outcome="win", total_moves=1, total_time_ms=100.0, completed=8)
        path = exporter.export_csv(tmp_path)
        assert path.exists()

    def test_export_txt(self, greedy, tmp_path):
        from src.analysis.exporter import GameExporter
        exporter = GameExporter()
        exporter.start_game(seed=1, difficulty=1, strategy="greedy")
        exporter.end_game(outcome="win", total_moves=10, total_time_ms=1000.0, completed=8)
        path = exporter.export_txt(tmp_path)
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "策略量化分析" in text


# ═══════════════════════════════════════════════════
#  genetic.py 测试
# ═══════════════════════════════════════════════════

class TestGenetic:
    """遗传算法"""

    def test_evolve_returns_result(self):
        from src.analysis.genetic import GeneticOptimizer
        ga = GeneticOptimizer("greedy", {})
        result = ga.evolve(difficulty=1, pop_size=2, generations=1, games_per_eval=2)
        assert result.generations == 1
        assert result.best.fitness >= 0

    def test_evolve_with_params(self):
        from src.analysis.genetic import GeneticOptimizer
        ga = GeneticOptimizer("mcts", {"iterations": [100, 200]})
        result = ga.evolve(difficulty=1, pop_size=2, generations=1, games_per_eval=2)
        assert "iterations" in result.best.params

    def test_export(self, tmp_path):
        from src.analysis.genetic import GeneticOptimizer, GAResult, Gene
        ga = GeneticOptimizer("greedy", {})
        result = GAResult(best=Gene(params={}), generations=0)
        path = ga.export(result, tmp_path)
        assert path.exists()


# ═══════════════════════════════════════════════════
#  tournament.py 测试
# ═══════════════════════════════════════════════════

class TestTournament:
    """锦标赛"""

    def test_tournament_run(self):
        from src.analysis.tournament import Tournament
        t = Tournament()
        result = t.run(["greedy", "random"], difficulty=1, seeds=[1, 2, 3], max_moves=100)
        assert len(result.matches) == 1
        assert result.matches[0].total == 3

    def test_tournament_standings(self):
        from src.analysis.tournament import Tournament
        t = Tournament()
        result = t.run(["greedy", "random"], difficulty=1, seeds=[1, 2], max_moves=100)
        assert "greedy" in result.standings
        assert "random" in result.standings

    def test_tournament_export(self, tmp_path):
        from src.analysis.tournament import Tournament, TournamentResult
        t = Tournament()
        result = t.run(["greedy"], difficulty=1, seeds=[1], max_moves=100)
        path = t.export(result, tmp_path)
        assert path.exists()


# ═══════════════════════════════════════════════════
#  runner.py 测试
# ═══════════════════════════════════════════════════

class TestRunner:
    """实验运行器"""

    def test_experiment_runner_run(self):
        from src.analysis.runner import ExperimentRunner
        runner = ExperimentRunner()
        result = runner.run(
            strategies={"greedy": GreedyStrategy()},
            difficulty=1,
            seeds=[1, 2],
            max_moves=100,
        )
        assert "strategies" in result
        assert result["total_games"] == 2

    def test_benchmark_runner_run(self):
        from src.analysis.runner import BenchmarkRunner
        runner = BenchmarkRunner()
        result = runner.run(
            strategies={"greedy": GreedyStrategy()},
            difficulties=[1],
            num_games=2,
            max_moves=100,
        )
        assert "benchmarks" in result
        assert len(result["benchmarks"]) == 1
