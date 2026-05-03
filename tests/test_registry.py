"""
策略注册中心测试
覆盖：注册、获取、工厂延迟构建、自定义注册、错误处理
"""

import pytest
from src.strategy.registry import (
    get_strategy,
    get_factory,
    list_strategies,
    register_custom,
    _REGISTRY,
)


class TestGetStrategy:
    """get_strategy 核心功能"""

    def test_get_greedy(self):
        strategy = get_strategy("greedy")
        assert strategy.name == "greedy"

    def test_get_random(self):
        strategy = get_strategy("random")
        assert strategy.name == "random"

    def test_get_mcts(self):
        strategy = get_strategy("mcts")
        assert strategy.name == "mcts"

    def test_get_mcts_fast(self):
        strategy = get_strategy("mcts_fast")
        assert strategy.name == "mcts_fast"

    def test_get_mcts_deep(self):
        strategy = get_strategy("mcts_deep")
        assert strategy.name == "mcts_deep"

    def test_get_neural(self):
        strategy = get_strategy("neural")
        assert strategy.name == "neural"

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="未知策略"):
            get_strategy("nonexistent")

    def test_each_call_returns_new_instance(self):
        """工厂模式：每次调用返回新实例"""
        s1 = get_strategy("greedy")
        s2 = get_strategy("greedy")
        assert s1 is not s2


class TestGetFactory:
    """get_factory 功能"""

    def test_get_existing_factory(self):
        factory = get_factory("greedy")
        assert factory is not None
        assert factory.name == "greedy"

    def test_get_nonexistent_factory(self):
        factory = get_factory("nonexistent")
        assert factory is None


class TestListStrategies:
    """list_strategies 功能"""

    def test_returns_list(self):
        strategies = list_strategies()
        assert isinstance(strategies, list)
        assert len(strategies) >= 5

    def test_each_has_required_fields(self):
        for s in list_strategies():
            assert "name" in s
            assert "display_name" in s
            assert "description" in s

    def test_contains_all_builtins(self):
        names = {s["name"] for s in list_strategies()}
        assert "greedy" in names
        assert "random" in names
        assert "mcts" in names
        assert "neural" in names


class TestRegisterCustom:
    """自定义策略注册"""

    def test_register_and_retrieve(self, monkeypatch):
        """注册自定义策略后可以获取"""
        from src.strategy.compose import StrategyFn

        def my_strategy(state, rules):
            return None

        register_custom("test_custom", "测试策略", lambda: StrategyFn(my_strategy, "test_custom"), "测试用")
        strategy = get_strategy("test_custom")
        assert strategy.name == "test_custom"

        # 清理
        _REGISTRY.pop("test_custom", None)
