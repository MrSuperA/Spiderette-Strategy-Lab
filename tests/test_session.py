"""Tests for src.core.session — GameSession, StepRecord, GameResult."""

import pytest
from src.core.session import GameSession, StepRecord, GameResult
from src.core.types import Outcome
from src.core.rules import RulesEngine
from src.envs.simulator import SimulatorEnv
from src.strategy.compose import GreedyStrategy


@pytest.fixture
def env_and_strategy():
    env = SimulatorEnv(seed=42, difficulty=1)
    strategy = GreedyStrategy()
    return env, strategy


class TestGameSession:
    def test_run_returns_game_result(self, env_and_strategy):
        env, strategy = env_and_strategy
        session = GameSession(env, strategy, max_moves=50)
        result = session.run()
        assert isinstance(result, GameResult)

    def test_is_iterable(self, env_and_strategy):
        env, strategy = env_and_strategy
        session = GameSession(env, strategy, max_moves=10)
        steps = list(session)
        assert len(steps) > 0
        assert all(isinstance(s, StepRecord) for s in steps)

    def test_max_moves_limit(self, env_and_strategy):
        env, strategy = env_and_strategy
        session = GameSession(env, strategy, max_moves=3)
        result = session.run()
        assert result.total_moves <= 3

    def test_on_step_callback_called(self, env_and_strategy):
        env, strategy = env_and_strategy
        collected = []
        session = GameSession(env, strategy, max_moves=5, on_step=lambda s: collected.append(s))
        list(session)
        assert len(collected) > 0
        assert all(isinstance(s, StepRecord) for s in collected)

    def test_result_has_outcome(self, env_and_strategy):
        env, strategy = env_and_strategy
        result = GameSession(env, strategy, max_moves=20).run()
        assert isinstance(result.outcome, Outcome)

    def test_result_has_seed(self, env_and_strategy):
        env, strategy = env_and_strategy
        result = GameSession(env, strategy, max_moves=10).run()
        assert result.seed == 42


class TestStepRecord:
    def test_to_dict(self, env_and_strategy):
        env, strategy = env_and_strategy
        session = GameSession(env, strategy, max_moves=1)
        for step in session:
            d = step.to_dict()
            assert "step" in d
            assert "strategy" in d
            assert "elapsed_ms" in d
            assert "legal_moves" in d
            assert "state" in d
            break


class TestGameResult:
    def test_is_win_property(self):
        r = GameResult(outcome=Outcome.WIN)
        assert r.is_win is True

    def test_is_not_win(self):
        r = GameResult(outcome=Outcome.DEADLOCK)
        assert r.is_win is False

    def test_avg_step_ms(self):
        r = GameResult(outcome=Outcome.WIN, total_moves=10, total_time_ms=100.0)
        assert r.avg_step_ms == 10.0

    def test_avg_step_ms_zero_moves(self):
        r = GameResult(outcome=Outcome.DEADLOCK, total_moves=0, total_time_ms=0.0)
        assert r.avg_step_ms == 0.0

    def test_to_dict(self):
        r = GameResult(outcome=Outcome.WIN, total_moves=5, total_time_ms=50.0, seed=1, completed=8)
        d = r.to_dict()
        assert d["outcome"] == "win"
        assert d["total_moves"] == 5
        assert d["completed"] == 8
