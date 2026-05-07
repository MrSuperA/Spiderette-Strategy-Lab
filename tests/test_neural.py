"""
神经网络策略测试
覆盖：特征提取、MLP 前向传播、策略选择、训练器数据收集
"""

import pytest
import random
from src.core.rules import RulesEngine
from src.core.types import GameState
from src.envs.generator import generate_game
from src.strategy.neural import extract_features, SimpleMLP, NeuralStrategy


@pytest.fixture
def simple_state():
    return generate_game(seed=42, difficulty=1)


@pytest.fixture
def rules():
    return RulesEngine()


@pytest.fixture
def mlp():
    return SimpleMLP(input_size=58, hidden1=32, hidden2=16)


class TestExtractFeatures:
    """特征提取函数"""

    def test_returns_list(self, simple_state):
        feat = extract_features(simple_state)
        assert isinstance(feat, list)

    def test_feature_length(self, simple_state):
        feat = extract_features(simple_state)
        assert len(feat) == 58

    def test_all_floats(self, simple_state):
        feat = extract_features(simple_state)
        assert all(isinstance(f, float) for f in feat)

    def test_values_in_range(self, simple_state):
        feat = extract_features(simple_state)
        assert all(0.0 <= f <= 1.0 for f in feat)

    def test_different_seeds_different_features(self):
        s1 = generate_game(seed=1, difficulty=1)
        s2 = generate_game(seed=2, difficulty=1)
        f1 = extract_features(s1)
        f2 = extract_features(s2)
        assert f1 != f2

    def test_difficulty_affects_features(self):
        s1 = generate_game(seed=42, difficulty=1)
        s2 = generate_game(seed=42, difficulty=4)
        f1 = extract_features(s1)
        f2 = extract_features(s2)
        # 最后一维是 1花色标志，应不同
        assert f1[-1] != f2[-1]


class TestSimpleMLP:
    """MLP 前向传播"""

    def test_predict_returns_float(self, mlp, simple_state):
        feat = extract_features(simple_state)
        score = mlp.predict(feat)
        assert isinstance(score, float)

    def test_predict_in_range(self, mlp, simple_state):
        feat = extract_features(simple_state)
        score = mlp.predict(feat)
        assert 0.0 <= score <= 1.0

    def test_predict_batch(self, mlp):
        states = [generate_game(seed=i, difficulty=1) for i in range(1, 4)]
        feats = [extract_features(s) for s in states]
        scores = mlp.predict_batch(feats)
        assert len(scores) == 3
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_save_and_load(self, mlp, tmp_path):
        path = str(tmp_path / "test_model.npz")
        mlp.save(path)

        mlp2 = SimpleMLP(input_size=58, hidden1=32, hidden2=16)
        mlp2.load(path)

        feat = extract_features(generate_game(seed=42, difficulty=1))
        assert abs(mlp.predict(feat) - mlp2.predict(feat)) < 1e-6


class TestNeuralStrategy:
    """神经网络策略"""

    def test_name(self):
        strategy = NeuralStrategy()
        assert strategy.name == "neural"

    def test_choose_returns_move_or_none(self, rules, simple_state):
        strategy = NeuralStrategy()
        move = strategy.choose(simple_state, rules)
        # 应返回合法移动或 None
        if move is not None:
            legal = rules.legal_moves(simple_state)
            assert any(
                m.src_col == move.src_col and m.dst_col == move.dst_col
                for m in legal
            )

    def test_choose_none_on_terminal(self, rules):
        """终态时应返回 None"""
        from src.core.types import Outcome
        strategy = NeuralStrategy()
        # 构造一个终态（通过运行到底）
        from src.envs.simulator import SimulatorEnv
        from src.core.session import GameSession
        env = SimulatorEnv(seed=1, difficulty=1)
        session = GameSession(env, get_strategy_greedy(), max_moves=500)
        result = session.run()
        final_state = env.observe()
        if rules.is_terminal(final_state).value > 0:
            assert strategy.choose(final_state, rules) is None


def get_strategy_greedy():
    from src.strategy.compose import GreedyStrategy
    return GreedyStrategy()
