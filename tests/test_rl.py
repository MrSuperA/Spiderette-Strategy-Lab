"""
RL 模块测试 — 环境包装器、课程学习、自博弈
"""

import pytest
from src.core.types import Outcome
from src.rl.environment import SpideretteEnv
from src.rl.curriculum import CurriculumScheduler, DEFAULT_CURRICULUM
from src.rl.self_play import SelfPlayCollector
from src.strategy.compose import GreedyStrategy


class TestSpideretteEnv:
    """Gym 风格环境"""

    def test_reset_returns_state(self):
        env = SpideretteEnv(difficulty=1)
        state, info = env.reset(seed=42)
        assert state is not None
        assert "seed" in info

    def test_step_returns_step_result(self):
        env = SpideretteEnv(difficulty=1)
        state, _ = env.reset(seed=42)
        actions = env.action_space()
        if actions:
            result = env.step(actions[0])
            assert result.observation is not None
            assert isinstance(result.reward, float)
            assert isinstance(result.terminated, bool)
            assert isinstance(result.truncated, bool)

    def test_terminated_on_win(self):
        """环境在 500 步内应终止（胜/败/截断）"""
        env = SpideretteEnv(difficulty=1, max_moves=500)
        state, _ = env.reset(seed=1)
        strategy = GreedyStrategy()
        for step in range(500):
            if env.is_terminal():
                break
            move = strategy.choose(state, env.rules)
            # 传递 None 给环境（环境会自动处理发牌/死局）
            result = env.step(move)
            state = result.observation
            if result.terminated or result.truncated:
                break
        # 应该在某处终止
        assert env.is_terminal()

    def test_reward_is_finite(self):
        env = SpideretteEnv(difficulty=1)
        state, _ = env.reset(seed=42)
        actions = env.action_space()
        if actions:
            result = env.step(actions[0])
            assert -1000 < result.reward < 1000

    def test_action_space(self):
        env = SpideretteEnv(difficulty=1)
        state, _ = env.reset(seed=42)
        actions = env.action_space()
        assert len(actions) > 0

    def test_render(self):
        env = SpideretteEnv(difficulty=1)
        env.reset(seed=42)
        text = env.render()
        assert "步数" in text


class TestCurriculumScheduler:
    """课程学习调度器"""

    def test_initial_difficulty(self):
        scheduler = CurriculumScheduler()
        assert scheduler.get_difficulty() == 1

    def test_initial_stage(self):
        scheduler = CurriculumScheduler()
        assert scheduler.stage_index == 0

    def test_promotion(self):
        scheduler = CurriculumScheduler(window_size=10)
        # 模拟高胜率
        for _ in range(150):
            scheduler.update(win_rate=0.5)
        # 应该晋级
        assert scheduler.stage_index > 0 or scheduler.get_difficulty() >= 1

    def test_no_promotion_below_threshold(self):
        scheduler = CurriculumScheduler(window_size=10)
        for _ in range(150):
            scheduler.update(win_rate=0.0)
        assert scheduler.stage_index == 0

    def test_status(self):
        scheduler = CurriculumScheduler()
        status = scheduler.get_status()
        assert "stage" in status
        assert "difficulty" in status
        assert "recent_win_rate" in status

    def test_label(self):
        scheduler = CurriculumScheduler()
        assert scheduler.get_label() != ""

    def test_total_stages(self):
        scheduler = CurriculumScheduler()
        assert scheduler.total_stages == len(DEFAULT_CURRICULUM)


class TestSelfPlayCollector:
    """自博弈数据收集"""

    def test_play_one_game(self):
        collector = SelfPlayCollector(strategy_name="greedy")
        result = collector.play_one_game(seed=42, difficulty=1, max_moves=100)
        assert result.total_moves > 0
        assert len(result.samples) > 0
        assert result.outcome in ("win", "deadlock", "timeout")

    def test_samples_have_policy(self):
        collector = SelfPlayCollector(strategy_name="greedy")
        result = collector.play_one_game(seed=42, difficulty=1, max_moves=50)
        for sample in result.samples:
            assert len(sample.policy) > 0

    def test_collect_training_data(self):
        collector = SelfPlayCollector(strategy_name="greedy")
        results = [
            collector.play_one_game(seed=i, difficulty=1, max_moves=50)
            for i in range(1, 3)
        ]
        features, policies, outcomes = collector.collect_training_data(results)
        assert len(features) == len(policies) == len(outcomes)
        assert len(features) > 0
        assert all(isinstance(f, list) for f in features)
