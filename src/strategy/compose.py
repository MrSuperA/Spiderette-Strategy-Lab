"""
策略组合器 — 装饰器模式，替代继承树
设计原则：策略即函数，装饰器增强行为但不改变签名
"""

from __future__ import annotations

import random
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Sequence

from src.core.types import GameState, Move, Rules, Strategy
from src.strategy.heuristics import assess_complexity, rank_moves


# ═══════════════════════════════════════════════════
#  策略包装器（将函数适配为 Strategy 协议）
# ═══════════════════════════════════════════════════

class StrategyFn:
    """将一个 (state, rules) → Move 的函数包装为 Strategy 对象"""

    def __init__(self, fn, label: str = "fn"):
        self._fn = fn
        self._label = label

    @property
    def name(self) -> str:
        return self._label

    def choose(self, state: GameState, rules: Rules) -> Optional[Move]:
        return self._fn(state, rules)


# ═══════════════════════════════════════════════════
#  基础策略
# ═══════════════════════════════════════════════════

def greedy(state: GameState, rules: Rules) -> Optional[Move]:
    """贪心策略：选优先级最高的移动"""
    if rules.is_terminal(state).value > 0:
        return None
    moves = rules.legal_moves(state)
    if not moves:
        return None
    ranked = rank_moves(state, moves)
    return ranked[0] if ranked else moves[0]


def random_choice(state: GameState, rules: Rules) -> Optional[Move]:
    """随机策略：均匀随机选择"""
    moves = rules.legal_moves(state)
    if not moves:
        return None
    return random.choice(moves)


# 工厂
def GreedyStrategy() -> StrategyFn:
    return StrategyFn(greedy, "greedy")


def RandomStrategy() -> StrategyFn:
    return StrategyFn(random_choice, "random")


# ═══════════════════════════════════════════════════
#  装饰器：缓存
# ═══════════════════════════════════════════════════

def with_cache(strategy: Strategy, capacity: int = 10000) -> Strategy:
    """给任意策略加 LRU 缓存"""
    _cache: OrderedDict[int, Optional[Move]] = OrderedDict()

    def cached_choose(state: GameState, rules: Rules) -> Optional[Move]:
        key = hash(state)
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        result = strategy.choose(state, rules)
        if len(_cache) >= capacity:
            _cache.popitem(last=False)
        _cache[key] = result
        return result

    return StrategyFn(cached_choose, f"cached({strategy.name})")


# ═══════════════════════════════════════════════════
#  装饰器：自适应深度
# ═══════════════════════════════════════════════════

def with_adaptive_depth(
    strategy_factory,
    *,
    fast_kwargs: dict,
    medium_kwargs: dict,
    deep_kwargs: dict,
) -> Strategy:
    """
    根据局面复杂度自动切换策略参数

    strategy_factory: 接受 kwargs 返回 Strategy 的工厂函数
    """
    _fast = strategy_factory(**fast_kwargs, label="adaptive_fast")
    _medium = strategy_factory(**medium_kwargs, label="adaptive_medium")
    _deep = strategy_factory(**deep_kwargs, label="adaptive_deep")

    def adaptive_choose(state: GameState, rules: Rules) -> Optional[Move]:
        complexity = assess_complexity(state)
        if complexity > 0.7:
            return _deep.choose(state, rules)
        elif complexity > 0.3:
            return _medium.choose(state, rules)
        else:
            return _fast.choose(state, rules)

    return StrategyFn(adaptive_choose, "adaptive")


# ═══════════════════════════════════════════════════
#  装饰器：并行
# ═══════════════════════════════════════════════════

def with_parallel(strategy: Strategy, workers: int = 4) -> Strategy:
    """
    并行化：多个独立 MCTS 搜索实例并行运行，加权投票合并
    注意：使用 ThreadPoolExecutor 避免跨进程序列化 GameState 的开销
    """
    def parallel_choose(state: GameState, rules: Rules) -> Optional[Move]:
        def _run_one(_):
            return strategy.choose(state, rules)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_run_one, range(workers)))

        return _weighted_vote(results)

    return StrategyFn(parallel_choose, f"parallel({strategy.name}, w={workers})")


def _weighted_vote(moves: list[Optional[Move]]) -> Optional[Move]:
    """加权投票：选择出现次数最多的移动"""
    counts: dict[Optional[Move], int] = {}
    for m in moves:
        counts[m] = counts.get(m, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda m: counts[m])


# ═══════════════════════════════════════════════════
#  装饰器：限时
# ═══════════════════════════════════════════════════

def with_time_limit(strategy: Strategy, seconds: float = 1.0) -> Strategy:
    """限时装饰器：超时则回退到贪心"""

    def timed_choose(state: GameState, rules: Rules) -> Optional[Move]:
        t0 = time.perf_counter()
        result = strategy.choose(state, rules)
        elapsed = time.perf_counter() - t0
        if elapsed > seconds:
            # 超时，回退到贪心
            return greedy(state, rules)
        return result

    return StrategyFn(timed_choose, f"timed({strategy.name}, {seconds}s)")


# ═══════════════════════════════════════════════════
#  装饰器：日志
# ═══════════════════════════════════════════════════

def with_logging(strategy: Strategy, log_fn=None) -> Strategy:
    """日志装饰器：记录每次决策"""
    if log_fn is None:
        log_fn = print

    def logging_choose(state: GameState, rules: Rules) -> Optional[Move]:
        t0 = time.perf_counter()
        result = strategy.choose(state, rules)
        elapsed = (time.perf_counter() - t0) * 1000
        log_fn(f"[{strategy.name}] move={result} elapsed={elapsed:.1f}ms")
        return result

    return StrategyFn(logging_choose, f"logged({strategy.name})")
