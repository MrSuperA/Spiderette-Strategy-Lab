"""Tests for src.strategy.compose — StrategyFn, greedy, with_cache, with_time_limit."""

import pytest

from src.core.types import Move, Strategy
from src.core.rules import RulesEngine
from src.envs.generator import generate_game
from src.strategy.compose import (
    StrategyFn,
    greedy,
    random_choice,
    with_cache,
    with_time_limit,
    with_logging,
    GreedyStrategy,
    RandomStrategy,
)


@pytest.fixture
def state():
    return generate_game(seed=42, difficulty=1)


@pytest.fixture
def rules():
    return RulesEngine()


class TestStrategyFn:
    def test_wraps_function_as_strategy(self):
        def my_fn(state, rules):
            return None

        s = StrategyFn(my_fn, "test")
        assert isinstance(s, Strategy)
        assert s.name == "test"

    def test_choose_delegates(self, state, rules):
        moves = rules.legal_moves(state)
        expected = moves[0] if moves else None

        def first_move(state, rules):
            m = rules.legal_moves(state)
            return m[0] if m else None

        s = StrategyFn(first_move, "first")
        result = s.choose(state, rules)
        assert result == expected


class TestGreedy:
    def test_returns_move(self, state, rules):
        move = greedy(state, rules)
        if move is not None:
            assert isinstance(move, Move)

    def test_returns_none_when_no_moves(self, make_state, rules):
        state = make_state(completed=8)
        move = greedy(state, rules)
        assert move is None


class TestGreedyStrategy:
    def test_satisfies_protocol(self):
        s = GreedyStrategy()
        assert isinstance(s, Strategy)

    def test_name(self):
        s = GreedyStrategy()
        assert s.name == "greedy"


class TestRandomChoice:
    def test_returns_move(self, state, rules):
        move = random_choice(state, rules)
        if move is not None:
            assert isinstance(move, Move)


class TestWithCache:
    def test_caches_results(self, state, rules):
        call_count = 0

        def counting_fn(st, ru):
            nonlocal call_count
            call_count += 1
            m = ru.legal_moves(st)
            return m[0] if m else None

        base = StrategyFn(counting_fn, "counting")
        cached = with_cache(base)
        cached.choose(state, rules)
        cached.choose(state, rules)
        # Should only call the underlying function once (cache hit on second call)
        assert call_count == 1

    def test_preserves_name(self):
        base = StrategyFn(lambda s, r: None, "my_strat")
        cached = with_cache(base)
        assert "cached" in cached.name
        assert "my_strat" in cached.name


class TestWithTimeLimit:
    def test_does_not_break_strategy(self, state, rules):
        base = GreedyStrategy()
        timed = with_time_limit(base, seconds=10.0)
        move = timed.choose(state, rules)
        if move is not None:
            assert isinstance(move, Move)

    def test_preserves_name(self):
        base = GreedyStrategy()
        timed = with_time_limit(base, seconds=5.0)
        assert "timed" in timed.name


class TestWithLogging:
    def test_does_not_break_strategy(self, state, rules):
        logs = []
        base = GreedyStrategy()
        logged = with_logging(base, log_fn=lambda msg: logs.append(msg))
        logged.choose(state, rules)
        assert len(logs) == 1
        assert "greedy" in logs[0]
