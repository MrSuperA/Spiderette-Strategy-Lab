"""Tests for src.analysis.metrics and src.analysis.report."""

import json
import pytest
from pathlib import Path

from src.core.session import GameResult
from src.core.types import Outcome
from src.analysis.metrics import StrategyStats, collect_stats, compare_strategies
from src.analysis.report import ReportGenerator


# ── Fixtures ──

@pytest.fixture
def sample_results():
    """Three game results: 2 wins, 1 deadlock."""
    return [
        GameResult(outcome=Outcome.WIN, total_moves=100, total_time_ms=500.0, seed=1, completed=8),
        GameResult(outcome=Outcome.WIN, total_moves=120, total_time_ms=600.0, seed=2, completed=8),
        GameResult(outcome=Outcome.DEADLOCK, total_moves=80, total_time_ms=400.0, seed=3, completed=3),
    ]


@pytest.fixture
def sample_stats(sample_results):
    return collect_stats("greedy", sample_results)


# ── collect_stats ──

class TestCollectStats:
    def test_aggregates_correctly(self, sample_results):
        stats = collect_stats("greedy", sample_results)
        assert stats.name == "greedy"
        assert stats.total_games == 3
        assert stats.wins == 2
        assert stats.deadlocks == 1
        assert stats.total_moves == 300
        assert stats.total_time_ms == 1500.0
        assert stats.completed_sum == 19

    def test_win_rate(self, sample_stats):
        assert abs(sample_stats.win_rate - 2 / 3) < 1e-6

    def test_avg_moves(self, sample_stats):
        assert abs(sample_stats.avg_moves - 100.0) < 1e-6

    def test_empty_results(self):
        stats = collect_stats("empty", [])
        assert stats.total_games == 0
        assert stats.win_rate == 0.0


# ── StrategyStats ──

class TestStrategyStats:
    def test_win_rate_ci95_valid_range(self, sample_stats):
        lo, hi = sample_stats.win_rate_ci95
        assert 0.0 <= lo <= hi <= 1.0

    def test_ci95_zero_games(self):
        stats = StrategyStats(name="empty")
        lo, hi = stats.win_rate_ci95
        assert lo == 0.0
        assert hi == 0.0

    def test_to_dict(self, sample_stats):
        d = sample_stats.to_dict()
        assert d["name"] == "greedy"
        assert d["total_games"] == 3
        assert d["wins"] == 2
        assert "win_rate_ci95" in d
        assert isinstance(d["win_rate_ci95"], list)


# ── compare_strategies ──

class TestCompareStrategies:
    def test_returns_expected_structure(self, sample_stats):
        other = StrategyStats(name="random", total_games=3, wins=1, deadlocks=2)
        result = compare_strategies([sample_stats, other])
        assert "strategies" in result
        assert "rankings" in result
        assert "best_win_rate" in result["rankings"]
        assert "total_games" in result
        assert result["total_games"] == 6

    def test_best_win_rate(self, sample_stats):
        other = StrategyStats(name="random", total_games=3, wins=1, deadlocks=2)
        result = compare_strategies([sample_stats, other])
        assert result["rankings"]["best_win_rate"]["name"] == "greedy"

    def test_empty_list(self):
        result = compare_strategies([])
        assert result == {}


# ── ReportGenerator ──

class TestReportGenerator:
    def test_export_json(self, sample_stats, tmp_path):
        gen = ReportGenerator([sample_stats], experiment_name="test_exp")
        gen.export(tmp_path, formats=("json",))
        json_path = tmp_path / "report.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["experiment"] == "test_exp"
        assert "comparison" in data

    def test_export_csv(self, sample_stats, tmp_path):
        gen = ReportGenerator([sample_stats])
        gen.export(tmp_path, formats=("csv",))
        csv_path = tmp_path / "report.csv"
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        assert "greedy" in content

    def test_export_markdown(self, sample_stats, tmp_path):
        gen = ReportGenerator([sample_stats], experiment_name="MD Test")
        gen.export(tmp_path, formats=("markdown",))
        md_path = tmp_path / "report.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "MD Test" in content
        assert "greedy" in content
