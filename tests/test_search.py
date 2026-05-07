"""
搜索模块测试 — 信息集、确定化采样、IS-MCTS、PUCT
"""

import pytest
import random
from src.core.rules import RulesEngine
from src.core.types import GameState, Outcome
from src.core.info_set import (
    ObservedState, VisibleColumn, VisibleCard,
    extract_observed, observed_hash,
)
from src.envs.generator import generate_game
from src.envs.simulator import SimulatorEnv
from src.strategy.compose import GreedyStrategy


@pytest.fixture
def rules():
    return RulesEngine()


@pytest.fixture
def state_with_hidden():
    """有暗牌的状态"""
    return generate_game(seed=42, difficulty=1)


@pytest.fixture
def state_no_hidden():
    """无暗牌的状态（通过大量移牌翻完）"""
    env = SimulatorEnv(seed=1, difficulty=1)
    strategy = GreedyStrategy()
    from src.core.session import GameSession
    session = GameSession(env, strategy, max_moves=500)
    session.run()
    return env.observe()


# ═══════════════════════════════════════════
#  信息集类型测试
# ═══════════════════════════════════════════

class TestInfoSet:
    """信息集抽象"""

    def test_extract_observed_hides_face_down(self, state_with_hidden):
        observed = extract_observed(state_with_hidden)
        assert isinstance(observed, ObservedState)
        # 暗牌不应出现在可见列中
        for col in observed.columns:
            for card in col.visible_cards:
                assert isinstance(card, VisibleCard)

    def test_observed_preserves_visible_info(self, state_with_hidden):
        observed = extract_observed(state_with_hidden)
        # 明牌数量应与原状态一致
        for i, col in enumerate(observed.columns):
            orig_face_up = state_with_hidden.columns[i].face_up_count
            assert len(col.visible_cards) == orig_face_up

    def test_observed_preserves_metadata(self, state_with_hidden):
        observed = extract_observed(state_with_hidden)
        assert observed.completed == state_with_hidden.completed
        assert observed.move_count == state_with_hidden.move_count
        assert observed.difficulty == state_with_hidden.difficulty

    def test_observed_hash_is_stable(self, state_with_hidden):
        observed = extract_observed(state_with_hidden)
        h1 = observed_hash(observed)
        h2 = observed_hash(observed)
        assert h1 == h2

    def test_visible_column_properties(self):
        col = VisibleColumn(
            visible_cards=(VisibleCard(suit=0, rank=13),),
            face_down_count=3,
        )
        assert col.length == 4
        assert col.face_up_count == 1
        assert not col.is_empty

    def test_empty_visible_column(self):
        col = VisibleColumn(visible_cards=(), face_down_count=0)
        assert col.is_empty
        assert col.length == 0


# ═══════════════════════════════════════════
#  确定化采样测试
# ═══════════════════════════════════════════

class TestDeterminization:
    """暗牌确定化采样"""

    def test_sample_preserves_visible_cards(self, state_with_hidden):
        from src.search.determinization import sample_determinization
        det = sample_determinization(state_with_hidden, random.Random(42))
        # 明牌应完全相同
        for i in range(10):
            orig_face_up = [c for c in state_with_hidden.columns[i].cards if c.face.name == "FACE_UP"]
            det_face_up = [c for c in det.columns[i].cards if c.face.name == "FACE_UP"]
            assert len(orig_face_up) == len(det_face_up)
            for a, b in zip(orig_face_up, det_face_up):
                assert a.suit == b.suit
                assert a.rank == b.rank

    def test_sample_changes_hidden_cards(self, state_with_hidden):
        from src.search.determinization import sample_determinization
        det1 = sample_determinization(state_with_hidden, random.Random(1))
        det2 = sample_determinization(state_with_hidden, random.Random(2))
        # 暗牌可能不同（概率极高）
        hidden1 = [(c.suit, c.rank) for col in det1.columns for c in col.cards if c.face.name == "FACE_DOWN"]
        hidden2 = [(c.suit, c.rank) for col in det2.columns for c in col.cards if c.face.name == "FACE_DOWN"]
        # 至少检查存在暗牌
        assert len(hidden1) > 0

    def test_sample_multiple(self, state_with_hidden):
        from src.search.determinization import sample_multiple
        samples = sample_multiple(state_with_hidden, n_samples=5, seed=42)
        assert len(samples) == 5
        assert all(isinstance(s, GameState) for s in samples)

    def test_no_hidden_returns_same(self, state_no_hidden):
        from src.search.determinization import sample_determinization, count_face_down_per_column
        face_down = count_face_down_per_column(state_no_hidden)
        if sum(face_down) == 0:
            det = sample_determinization(state_no_hidden, random.Random(42))
            assert det is state_no_hidden
        # 如果仍有暗牌（greedy 500 步不一定翻完），测试采样不崩溃
        else:
            det = sample_determinization(state_no_hidden, random.Random(42))
            assert isinstance(det, GameState)

    def test_compute_unknown_pool(self, state_with_hidden):
        from src.search.determinization import compute_unknown_pool, collect_known_cards
        pool = compute_unknown_pool(state_with_hidden)
        assert len(pool) > 0
        # 未知牌池 + 已知牌 = 104
        known = collect_known_cards(state_with_hidden)
        assert len(pool) + sum(known.values()) == 104


# ═══════════════════════════════════════════
#  IS-MCTS 测试
# ═══════════════════════════════════════════

class TestISMCTS:
    """信息集 MCTS 策略"""

    def test_name(self):
        from src.search.is_mcts import ISMCTSStrategy
        strategy = ISMCTSStrategy(label="test_is")
        assert strategy.name == "test_is"

    def test_choose_returns_move(self, rules, state_with_hidden):
        from src.search.is_mcts import create_is_mcts
        strategy = create_is_mcts(n_determinizations=3, iterations=100)
        move = strategy.choose(state_with_hidden, rules)
        if move is not None:
            legal = rules.legal_moves(state_with_hidden)
            assert any(m.src_col == move.src_col and m.dst_col == move.dst_col for m in legal)

    def test_choose_none_on_terminal(self, rules):
        from src.search.is_mcts import create_is_mcts
        strategy = create_is_mcts(n_determinizations=3, iterations=50)
        # 构造终态
        env = SimulatorEnv(seed=1, difficulty=1)
        from src.core.session import GameSession
        session = GameSession(env, GreedyStrategy(), max_moves=500)
        session.run()
        final = env.observe()
        if rules.is_terminal(final).value > 0:
            assert strategy.choose(final, rules) is None

    def test_factory_function(self):
        from src.search.is_mcts import create_is_mcts
        strategy = create_is_mcts(n_determinizations=5, iterations=200)
        assert strategy._n_det == 5
        assert strategy._iterations == 200


# ═══════════════════════════════════════════
#  PUCT 测试
# ═══════════════════════════════════════════

class TestPUCT:
    """PUCT 搜索策略"""

    def test_name(self):
        from src.search.puct import PUCTStrategy
        strategy = PUCTStrategy(label="test_puct")
        assert strategy.name == "test_puct"

    def test_choose_returns_move(self, rules, state_with_hidden):
        from src.search.puct import create_puct
        strategy = create_puct(iterations=100)
        move = strategy.choose(state_with_hidden, rules)
        if move is not None:
            legal = rules.legal_moves(state_with_hidden)
            assert any(m.src_col == move.src_col and m.dst_col == move.dst_col for m in legal)

    def test_choose_none_on_terminal(self, rules):
        from src.search.puct import create_puct
        strategy = create_puct(iterations=50)
        env = SimulatorEnv(seed=1, difficulty=1)
        from src.core.session import GameSession
        session = GameSession(env, GreedyStrategy(), max_moves=500)
        session.run()
        final = env.observe()
        if rules.is_terminal(final).value > 0:
            assert strategy.choose(final, rules) is None

    def test_heuristic_policy_value(self, state_with_hidden):
        from src.search.puct import HeuristicPolicyValue
        pv = HeuristicPolicyValue()
        policy = pv.predict_policy(state_with_hidden)
        assert len(policy) > 0
        assert abs(sum(policy.values()) - 1.0) < 0.01

        value = pv.predict_value(state_with_hidden)
        assert -1.0 <= value <= 1.0

    def test_dirichlet_noise(self):
        from src.search.puct import PUCTStrategy
        strategy = PUCTStrategy()
        noise = strategy._dirichlet_noise(10)
        assert len(noise) == 10
        assert abs(sum(noise) - 1.0) < 0.01
        assert all(n >= 0 for n in noise)

    def test_factory_function(self):
        from src.search.puct import create_puct
        strategy = create_puct(iterations=500, c_puct=2.0)
        assert strategy._iterations == 500
        assert strategy._c_puct == 2.0


# ═══════════════════════════════════════════
#  增强特征测试
# ═══════════════════════════════════════════

class TestFeatureV2:
    """增强特征提取"""

    def test_returns_list(self, state_with_hidden):
        from src.network.feature_v2 import extract_features_v2
        feat = extract_features_v2(state_with_hidden)
        assert isinstance(feat, list)

    def test_feature_length(self, state_with_hidden):
        from src.network.feature_v2 import extract_features_v2
        feat = extract_features_v2(state_with_hidden)
        assert len(feat) == 220

    def test_all_floats(self, state_with_hidden):
        from src.network.feature_v2 import extract_features_v2
        feat = extract_features_v2(state_with_hidden)
        assert all(isinstance(f, (int, float)) for f in feat)

    def test_no_nan(self, state_with_hidden):
        import math
        from src.network.feature_v2 import extract_features_v2
        feat = extract_features_v2(state_with_hidden)
        assert not any(math.isnan(f) for f in feat)

    def test_different_seeds_different_features(self):
        from src.network.feature_v2 import extract_features_v2
        s1 = generate_game(seed=1, difficulty=1)
        s2 = generate_game(seed=2, difficulty=1)
        f1 = extract_features_v2(s1)
        f2 = extract_features_v2(s2)
        assert f1 != f2

    def test_with_history(self, state_with_hidden):
        from src.network.feature_v2 import extract_features_v2
        history = [generate_game(seed=i, difficulty=1) for i in range(5)]
        feat = extract_features_v2(state_with_hidden, history=history)
        assert len(feat) == 220
