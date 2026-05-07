"""
MCTS 策略 — 蒙特卡洛树搜索核心算法
设计原则：策略即函数（满足 Strategy 协议），通过 partial 绑定参数
四阶段：Selection → Expansion → Simulation → Backpropagation
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

from src.core.types import GameState, Move, Outcome, Rules, Strategy
from src.strategy.heuristics import (
    assess_complexity,
    evaluate,
    heuristic_rollout,
    rank_moves,
)


# ═══════════════════════════════════════════════════
#  MCTS 节点
# ═══════════════════════════════════════════════════

class MCTSNode:
    """MCTS 搜索树节点 — __slots__ 优化内存"""
    __slots__ = (
        "state", "move", "parent", "children",
        "visits", "total_score", "untried_moves", "depth", "is_terminal",
    )

    def __init__(
        self,
        state: GameState,
        move: Optional[Move] = None,
        parent: Optional[MCTSNode] = None,
        depth: int = 0,
        is_terminal: bool = False,
    ):
        self.state = state
        self.move = move
        self.parent = parent
        self.children: list[MCTSNode] = []
        self.visits = 0
        self.total_score = 0.0
        self.untried_moves: list[Move] = []
        self.depth = depth
        self.is_terminal = is_terminal

    @property
    def avg_score(self) -> float:
        return self.total_score / self.visits if self.visits > 0 else 0.0

    @property
    def is_fully_expanded(self) -> bool:
        return len(self.untried_moves) == 0

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def ucb1(self, child: MCTSNode, exploration: float = 1.4) -> float:
        """UCB1 评分公式 — 使用 tanh 压缩，不依赖固定分数范围"""
        if child.visits == 0:
            return float("inf")
        exploit = math.tanh(child.avg_score / 50.0)  # tanh 压缩到 (-1, 1)
        explore = exploration * math.sqrt(math.log(self.visits) / child.visits)
        return exploit + explore

    def best_child(self, exploration: float = 1.4) -> Optional[MCTSNode]:
        """选择 UCB1 最高的子节点"""
        if not self.children:
            return None
        return max(self.children, key=lambda c: self.ucb1(c, exploration))

    def update(self, score: float) -> None:
        """回溯更新"""
        self.visits += 1
        self.total_score += score

    def to_dict(self, max_depth: int = 3, max_children: int = 5) -> dict:
        """序列化为可前端渲染的树结构"""
        d = {
            "visits": self.visits,
            "score": round(self.avg_score, 2),
            "move": self.move.to_dict() if self.move else None,
        }
        if self.children and max_depth > 0:
            sorted_children = sorted(self.children, key=lambda c: -c.visits)
            d["children"] = [
                c.to_dict(max_depth - 1, max_children)
                for c in sorted_children[:max_children]
            ]
        return d


# ═══════════════════════════════════════════════════
#  LRU 记忆缓存
# ═══════════════════════════════════════════════════

class MCTSMemory:
    """轻量级 LRU 缓存，存储状态评估结果"""

    def __init__(self, capacity: int = 10000):
        from collections import OrderedDict
        self._cache: OrderedDict[int, tuple[float, float]] = OrderedDict()
        self._capacity = capacity
        self._hits = 0
        self._misses = 0

    def get(self, state: GameState) -> Optional[tuple[float, float]]:
        key = hash(state)
        result = self._cache.get(key)
        if result is not None:
            self._cache.move_to_end(key)
            self._hits += 1
        else:
            self._misses += 1
        return result

    def put(self, state: GameState, score: float, confidence: float) -> None:
        key = hash(state)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = (score, confidence)
            return
        if len(self._cache) >= self._capacity:
            self._cache.popitem(last=False)
        self._cache[key] = (score, confidence)

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        return len(self._cache)


# ═══════════════════════════════════════════════════
#  MCTS 策略（满足 Strategy 协议）
# ═══════════════════════════════════════════════════

class MCTSStrategy:
    """
    MCTS 策略 — 通过构造参数控制行为，无需子类

    用法::

        strategy = MCTSStrategy(iterations=1000, time_limit=1.0)
        move = strategy.choose(state, rules)
    """

    def __init__(
        self,
        *,
        iterations: int = 1000,
        time_limit: float = 1.0,
        exploration: float = 1.4,
        use_heuristic: bool = True,
        use_memory: bool = True,
        memory_size: int = 10000,
        rollout_depth: int = 30,
        convergence_threshold: float = 0.7,
        convergence_min_visits: int = 50,
        label: str = "mcts",
    ):
        self._iterations = iterations
        self._time_limit = time_limit
        self._exploration = exploration
        self._use_heuristic = use_heuristic
        self._use_memory = use_memory
        self._rollout_depth = rollout_depth
        self._convergence_threshold = convergence_threshold
        self._convergence_min_visits = convergence_min_visits
        self._label = label
        self._memory = MCTSMemory(memory_size) if use_memory else None
        self._rng = random.Random(42)

        # 运行时统计
        self._last_iterations = 0
        self._last_tree_size = 0
        self._last_root: Optional[MCTSNode] = None

    @property
    def name(self) -> str:
        return self._label

    @property
    def last_iterations(self) -> int:
        return self._last_iterations

    @property
    def last_tree_size(self) -> int:
        return self._last_tree_size

    @property
    def memory_hit_rate(self) -> float:
        return self._memory.hit_rate if self._memory else 0.0

    def choose(self, state: GameState, rules: Rules) -> Optional[Move]:
        """选择最佳移动"""
        if rules.is_terminal(state).value > 0:
            return None
        moves = rules.legal_moves(state)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        # 记忆缓存查找
        if self._memory:
            cached = self._memory.get(state)
            if cached and cached[1] > 0.9:
                return self._find_move_by_score(moves, cached[0], state, rules)

        # 构建根节点
        root = MCTSNode(state=state, depth=0)
        root.untried_moves = rank_moves(state, moves) if self._use_heuristic else list(moves)

        # MCTS 搜索
        t0 = time.perf_counter()
        iterations = 0

        for _ in range(self._iterations):
            if time.perf_counter() - t0 > self._time_limit:
                break

            # Selection + Expansion
            node = self._select(root)
            if not node.is_terminal and not node.is_fully_expanded:
                node = self._expand(node, rules)

            # Simulation
            score = self._simulate(node.state, rules)

            # Backpropagation
            self._backpropagate(node, score)
            iterations += 1

            # 收敛检测
            if iterations % 50 == 0 and iterations > 100:
                if self._check_convergence(root):
                    break

        # 更新统计
        self._last_iterations = iterations
        self._last_tree_size = self._count_nodes(root)
        self._last_root = root

        # 选择最佳移动
        best = self._select_best(root)
        if best and self._memory:
            confidence = best.visits / max(1, root.visits)
            self._memory.put(state, best.avg_score, confidence)

        return best.move if best else moves[0]

    def get_search_tree(self) -> Optional[dict]:
        """获取搜索树数据（供前端可视化）"""
        if self._last_root:
            return self._last_root.to_dict(max_depth=3, max_children=5)
        return None

    # ── MCTS 四阶段 ──

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Selection：沿 UCB1 向下选择到叶节点或未完全扩展节点"""
        current = node
        while not current.is_leaf and current.is_fully_expanded:
            best = current.best_child(self._exploration)
            if best is None:
                break
            current = best
        return current

    def _expand(self, node: MCTSNode, rules: Rules) -> MCTSNode:
        """Expansion：从 untried_moves 中扩展一个子节点"""
        if not node.untried_moves:
            return node

        move = node.untried_moves.pop()
        new_state = rules.apply_move(node.state, move)
        is_terminal = rules.is_terminal(new_state).value > 0

        child = MCTSNode(
            state=new_state,
            move=move,
            parent=node,
            depth=node.depth + 1,
            is_terminal=is_terminal,
        )

        if not is_terminal:
            child_moves = rules.legal_moves(new_state)
            child.untried_moves = (
                rank_moves(new_state, child_moves) if self._use_heuristic
                else list(child_moves)
            )

        node.children.append(child)
        return child

    def _simulate(self, state: GameState, rules: Rules) -> float:
        """Simulation：启发式引导的快速模拟"""
        if rules.is_win(state):
            return 100.0
        if rules.is_terminal(state) == Outcome.DEADLOCK:
            return -50.0

        if self._use_heuristic:
            return heuristic_rollout(
                state, rules,
                max_depth=self._rollout_depth,
                rng=self._rng,
            )

        # 纯随机模拟
        current = state
        for _ in range(self._rollout_depth):
            outcome = rules.is_terminal(current)
            if outcome.value > 0:
                return 100.0 if outcome == Outcome.WIN else -50.0
            moves = rules.legal_moves(current)
            if not moves:
                if rules.can_deal(current):
                    current = rules.deal(current)
                    continue
                return -50.0
            current = rules.apply_move(current, self._rng.choice(moves))
        return evaluate(current)

    def _backpropagate(self, node: MCTSNode, score: float) -> None:
        """Backpropagation：沿路径向上传播分数"""
        current: Optional[MCTSNode] = node
        while current is not None:
            current.update(score)
            current = current.parent

    def _select_best(self, root: MCTSNode) -> Optional[MCTSNode]:
        """选择访问次数最多的子节点（最稳健的选择）"""
        if not root.children:
            return None
        return max(root.children, key=lambda c: c.visits)

    def _check_convergence(self, root: MCTSNode) -> bool:
        """检查搜索是否已收敛 — 复杂局面用更高阈值，避免过早停止"""
        if not root.children:
            return False
        best = max(root.children, key=lambda c: c.visits)
        ratio = best.visits / max(1, root.visits)
        # 根据局面复杂度动态调整阈值：复杂局面需要更多探索
        complexity = assess_complexity(root.state)
        adjusted_threshold = self._convergence_threshold + complexity * 0.15
        adjusted_min_visits = int(self._convergence_min_visits * (1 + complexity * 0.5))
        return (ratio >= adjusted_threshold
                and best.visits >= adjusted_min_visits
                and best.avg_score > 0)

    def _count_nodes(self, node: MCTSNode) -> int:
        """统计搜索树节点数"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    def _find_move_by_score(
        self, moves: Sequence[Move], cached_score: float, state: GameState, rules: Rules
    ) -> Move:
        """从缓存分数找到最接近的移动（评估全部合法移动）"""
        from src.strategy.heuristics import evaluate
        best_move = moves[0]
        best_diff = float("inf")
        for move in moves:
            new_state = rules.apply_move(state, move)
            score = evaluate(new_state)
            diff = abs(score - cached_score)
            if diff < best_diff:
                best_diff = diff
                best_move = move
        return best_move


# ═══════════════════════════════════════════════════
#  工厂函数（便捷创建）
# ═══════════════════════════════════════════════════

def create_mcts(
    iterations: int = 1000,
    time_limit: float = 1.0,
    exploration: float = 1.4,
    **kwargs,
) -> MCTSStrategy:
    """工厂函数：创建 MCTS 策略实例"""
    return MCTSStrategy(
        iterations=iterations,
        time_limit=time_limit,
        exploration=exploration,
        **kwargs,
    )


def create_mcts_deep(**kwargs) -> MCTSStrategy:
    """深度 MCTS：更高迭代、更长时限"""
    defaults = {"iterations": 2000, "time_limit": 2.0, "exploration": 1.2, "label": "mcts_deep"}
    defaults.update(kwargs)
    return MCTSStrategy(**defaults)


def create_mcts_fast(**kwargs) -> MCTSStrategy:
    """快速 MCTS：低迭代、短时限"""
    defaults = {"iterations": 300, "time_limit": 0.3, "label": "mcts_fast"}
    defaults.update(kwargs)
    return MCTSStrategy(**defaults)
