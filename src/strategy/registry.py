"""
策略注册中心 — 单一注册点，消除 4 处重复
所有策略在此注册，其他模块通过 registry 获取
"""

from __future__ import annotations

from typing import Optional

from src.core.types import Strategy


class StrategyFactory:
    """策略工厂：延迟构建，避免导入时实例化"""

    def __init__(self, name: str, display_name: str, factory_fn, description: str = ""):
        self.name = name
        self.display_name = display_name
        self.factory_fn = factory_fn
        self.description = description

    def create(self, **kwargs) -> Strategy:
        return self.factory_fn(**kwargs)


# ═══════════════════════════════════════════════════════════
#  策略注册表（唯一注册点）
# ═══════════════════════════════════════════════════════════

_REGISTRY: dict[str, StrategyFactory] = {}


def _register(name: str, display_name: str, factory_fn, description: str = "") -> None:
    _REGISTRY[name] = StrategyFactory(name, display_name, factory_fn, description)


# ── 内置策略注册 ──

def _create_mcts(**kwargs):
    from src.strategy.mcts import create_mcts
    return create_mcts(**kwargs)

def _create_mcts_fast(**kwargs):
    from src.strategy.mcts import create_mcts_fast
    return create_mcts_fast(**kwargs)

def _create_mcts_deep(**kwargs):
    from src.strategy.mcts import create_mcts_deep
    return create_mcts_deep(**kwargs)

def _create_greedy(**kwargs):
    from src.strategy.compose import GreedyStrategy
    return GreedyStrategy()

def _create_random(**kwargs):
    from src.strategy.compose import RandomStrategy
    return RandomStrategy()

def _create_neural(**kwargs):
    from src.strategy.neural import NeuralStrategy
    model_path = kwargs.pop("model_path", None)
    return NeuralStrategy(model_path=model_path)

def _create_is_mcts(**kwargs):
    from src.search.is_mcts import create_is_mcts
    return create_is_mcts(**kwargs)

def _create_puct(**kwargs):
    from src.search.puct import create_puct
    return create_puct(**kwargs)


_register("mcts", "MCTS", _create_mcts, "蒙特卡洛树搜索，200次迭代")
_register("mcts_fast", "MCTS 快速", _create_mcts_fast, "低迭代次数，适合批量")
_register("mcts_deep", "MCTS 深度", _create_mcts_deep, "高迭代次数，高质量")
_register("greedy", "贪心", _create_greedy, "启发式评分选择最优移动")
_register("random", "随机", _create_random, "随机选择合法移动（基线）")
_register("neural", "神经网络", _create_neural, "MLP 评估策略（需先训练模型）")
_register("is_mcts", "信息集MCTS", _create_is_mcts, "处理暗牌不完美信息的MCTS")
_register("puct", "PUCT搜索", _create_puct, "AlphaZero风格PUCT搜索，支持神经网络先验")


# ═══════════════════════════════════════════════════════════
#  公共 API
# ═══════════════════════════════════════════════════════════

def get_strategy(name: str, **kwargs) -> Strategy:
    """获取策略实例"""
    factory = _REGISTRY.get(name)
    if not factory:
        raise ValueError(f"未知策略: {name}，可用: {list(_REGISTRY.keys())}")
    return factory.create(**kwargs)


def get_factory(name: str) -> Optional[StrategyFactory]:
    """获取策略工厂"""
    return _REGISTRY.get(name)


def list_strategies() -> list[dict]:
    """列出所有注册策略"""
    return [
        {"name": f.name, "display_name": f.display_name, "description": f.description}
        for f in _REGISTRY.values()
    ]


def register_custom(name: str, display_name: str, factory_fn, description: str = "") -> None:
    """注册自定义策略（插件扩展点）"""
    _register(name, display_name, factory_fn, description)


def register_from_config(
    name: str,
    base_strategy: str,
    params: dict,
    display_name: str = "",
    description: str = "",
) -> None:
    """
    基于已有策略+参数字典注册一个命名变体

    用法::

        register_from_config("mcts_v2", "mcts", {"iterations": 2000, "exploration": 1.8})
        strategy = get_strategy("mcts_v2")
    """
    def factory(**kwargs):
        merged = {**params, **kwargs}
        return get_strategy(base_strategy, **merged)

    _register(
        name,
        display_name or f"{base_strategy} ({name})",
        factory,
        description or f"基于 {base_strategy} 的自定义变体，参数: {params}",
    )


def register_from_manifest(manifest_path: str) -> str:
    """
    从策略清单 JSON 文件注册策略

    Returns:
        注册的策略名
    """
    from src.iteration.engine import StrategyManifest
    manifest = StrategyManifest.load(manifest_path)
    register_from_config(
        name=manifest.name,
        base_strategy=manifest.name,
        params=manifest.params,
        display_name=manifest.display_name,
        description=f"从清单加载 v{manifest.version}: {manifest.notes}",
    )
    return manifest.name
