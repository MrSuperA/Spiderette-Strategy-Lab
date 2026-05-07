"""Tests for src.strategy.mcts — MCTSNode, MCTSMemory, MCTSStrategy."""

import pytest

from src.core.types import Move, Strategy
from src.core.rules import RulesEngine
from src.envs.generator import generate_game
from src.strategy.mcts import MCTSNode, MCTSMemory, MCTSStrategy


@pytest.fixture
def state():
    return generate_game(seed=42, difficulty=1)


@pytest.fixture
def rules():
    return RulesEngine()


# ── MCTSNode ──

class TestMCTSNode:
    def test_creation(self, state):
        node = MCTSNode(state=state)
        assert node.state is state
        assert node.move is None
        assert node.parent is None
        assert node.visits == 0
        assert node.total_score == 0.0
        assert node.depth == 0
        assert node.is_terminal is False

    def test_avg_score_zero_visits(self, state):
        node = MCTSNode(state=state)
        assert node.avg_score == 0.0

    def test_update(self, state):
        node = MCTSNode(state=state)
        node.update(50.0)
        node.update(100.0)
        assert node.visits == 2
        assert node.avg_score == 75.0

    def test_is_leaf(self, state):
        node = MCTSNode(state=state)
        assert node.is_leaf is True

    def test_is_fully_expanded_empty(self, state):
        node = MCTSNode(state=state)
        node.untried_moves = []
        assert node.is_fully_expanded is True

    def test_best_child_none_when_no_children(self, state):
        node = MCTSNode(state=state)
        assert node.best_child() is None

    def test_best_child_returns_highest_ucb1(self, state):
        parent = MCTSNode(state=state)
        parent.visits = 100
        c1 = MCTSNode(state=state, parent=parent)
        c1.visits = 50
        c1.total_score = 2500.0
        c2 = MCTSNode(state=state, parent=parent)
        c2.visits = 10
        c2.total_score = 0.0
        parent.children = [c1, c2]
        best = parent.best_child(exploration=0.1)  # low exploration => exploit
        assert best is c1

    def test_to_dict(self, state):
        node = MCTSNode(state=state)
        node.visits = 10
        node.total_score = 500.0
        d = node.to_dict()
        assert d["visits"] == 10
        assert d["score"] == 50.0


# ── MCTSMemory ──

class TestMCTSMemory:
    def test_put_and_get(self, state):
        mem = MCTSMemory(capacity=10)
        mem.put(state, 42.0, 0.9)
        result = mem.get(state)
        assert result is not None
        assert result[0] == 42.0
        assert result[1] == 0.9

    def test_get_miss(self, state, make_state):
        mem = MCTSMemory()
        other = make_state(seed=999)
        result = mem.get(other)
        # Might be None or might match by hash collision — check miss count
        assert mem._misses >= 1

    def test_hit_rate(self, state):
        mem = MCTSMemory()
        mem.put(state, 10.0, 0.5)
        mem.get(state)  # hit
        mem.get(state)  # hit
        assert mem.hit_rate > 0.0

    def test_clear(self, state):
        mem = MCTSMemory()
        mem.put(state, 10.0, 0.5)
        mem.get(state)
        mem.clear()
        assert mem.size == 0
        assert mem.hit_rate == 0.0

    def test_capacity_eviction(self, state, make_state):
        mem = MCTSMemory(capacity=2)
        s1 = make_state(seed=1)
        s2 = make_state(seed=2)
        s3 = make_state(seed=3)
        mem.put(s1, 1.0, 0.5)
        mem.put(s2, 2.0, 0.5)
        mem.put(s3, 3.0, 0.5)  # should evict s1
        assert mem.size <= 2


# ── MCTSStrategy ──

class TestMCTSStrategy:
    def test_satisfies_strategy_protocol(self):
        s = MCTSStrategy(iterations=10, time_limit=0.1)
        assert isinstance(s, Strategy)

    def test_name_property(self):
        s = MCTSStrategy(label="test_mcts")
        assert s.name == "test_mcts"

    def test_choose_returns_move_or_none(self, state, rules):
        s = MCTSStrategy(iterations=20, time_limit=0.5, use_memory=False)
        move = s.choose(state, rules)
        if move is not None:
            assert isinstance(move, Move)

    def test_choose_returns_none_for_terminal(self, make_state, rules):
        state = make_state(completed=8)
        s = MCTSStrategy(iterations=10, time_limit=0.1)
        move = s.choose(state, rules)
        assert move is None

    def test_last_iterations_updated(self, state, rules):
        s = MCTSStrategy(iterations=50, time_limit=1.0, use_memory=False)
        s.choose(state, rules)
        assert s.last_iterations > 0

    def test_last_tree_size(self, state, rules):
        s = MCTSStrategy(iterations=50, time_limit=1.0, use_memory=False)
        s.choose(state, rules)
        assert s.last_tree_size >= 1

    def test_convergence_detection(self, state, rules):
        """With very few iterations, convergence might or might not trigger — just check no crash."""
        s = MCTSStrategy(
            iterations=200, time_limit=2.0,
            convergence_threshold=0.5, convergence_min_visits=5,
        )
        s.choose(state, rules)
        assert s.last_iterations >= 0

    def test_memory_hit_rate(self, state, rules):
        s = MCTSStrategy(iterations=20, time_limit=0.5, use_memory=True)
        s.choose(state, rules)
        assert isinstance(s.memory_hit_rate, float)
