"""Tests for src.strategy.heuristics — evaluate, assess_complexity, rank_moves, heuristic_rollout."""

import pytest
import random as stdlib_random

from src.core.types import Move
from src.core.rules import RulesEngine
from src.envs.generator import generate_game
from src.strategy.heuristics import (
    assess_complexity,
    evaluate,
    heuristic_rollout,
    move_priority,
    rank_moves,
)


@pytest.fixture
def state():
    return generate_game(seed=42, difficulty=2)


@pytest.fixture
def rules():
    return RulesEngine()


class TestEvaluate:
    def test_returns_float(self, state):
        score = evaluate(state)
        assert isinstance(score, float)

    def test_in_range(self, state):
        score = evaluate(state)
        assert -100.0 <= score <= 100.0

    def test_higher_score_with_more_completed(self, make_state):
        low = make_state(completed=0)
        high = make_state(completed=5)
        assert evaluate(high) > evaluate(low)


class TestAssessComplexity:
    def test_returns_float(self, state):
        c = assess_complexity(state)
        assert isinstance(c, float)

    def test_in_range(self, state):
        c = assess_complexity(state)
        assert 0.0 <= c <= 1.0

    def test_initial_state_is_complex(self, state):
        """Initial state has many face-down cards, should be moderately complex."""
        c = assess_complexity(state)
        assert c > 0.3


class TestRankMoves:
    def test_returns_sorted_list(self, state, rules):
        moves = rules.legal_moves(state)
        if moves:
            ranked = rank_moves(state, moves)
            assert len(ranked) == len(moves)
            assert isinstance(ranked, list)

    def test_sorted_by_priority(self, state, rules):
        moves = rules.legal_moves(state)
        if len(moves) >= 2:
            ranked = rank_moves(state, moves)
            priorities = [move_priority(state, m) for m in ranked]
            for i in range(len(priorities) - 1):
                assert priorities[i] <= priorities[i + 1]


class TestHeuristicRollout:
    def test_returns_float(self, state, rules):
        result = heuristic_rollout(state, rules, max_depth=5, rng=stdlib_random.Random(0))
        assert isinstance(result, float)

    def test_win_returns_100(self, make_state, rules):
        """A terminal win state should return 100.0."""
        state = make_state(completed=8)
        result = heuristic_rollout(state, rules, max_depth=5, rng=stdlib_random.Random(0))
        assert result == 100.0

    def test_with_default_rng(self, state, rules):
        """Should work without providing an explicit rng."""
        result = heuristic_rollout(state, rules, max_depth=3)
        assert isinstance(result, float)
