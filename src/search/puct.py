"""
PUCT 搜索 — AlphaZero 风格的 MCTS，集成神经网络先验
核心改进：用 Policy Network 的先验概率引导搜索，用 Value Network 替代 rollout

PUCT 公式：Q(s,a) + c_puct * P(s,a) * sqrt(N(s)) / (1 + N(s,a))
"""

from __future__ import annotations

import math
import random
import time
from typing import Optional, Protocol, Sequence

from src.core.types import GameState, Move, Rules, Strategy
from src.strategy.heuristics import evaluate, rank_moves


class PolicyValueNetwork(Protocol):
    """策略-价值网络协议"""
    def predict_policy(self, state: GameState) -> dict[tuple[int, int], float]:
        """预测动作先验概率 {(src_col, dst_col): probability}"""
        ...
    def predict_value(self, state: GameState) -> float:
        """预测状态价值 [-1, 1]"""
        ...


class HeuristicPolicyValue:
    """
    基于启发式的策略-价值估计（不依赖神经网络）
    用于在没有训练好的网络时提供合理的先验概率和价值估计
    """

    def predict_policy(self, state: GameState) -> dict[tuple[int, int], float]:
        """基于 rank_moves 的优先级生成先验概率"""
        from src.core.rules import RulesEngine
        rules = RulesEngine()
        moves = rules.legal_moves(state)
        if not moves:
            return {}
        ranked = rank_moves(state, moves)
        # 指数衰减的先验概率
        probs = {}
        for i, move in enumerate(ranked):
            key = (move.src_col, move.dst_col)
            prob = math.exp(-0.3 * i)
            probs[key] = probs.get(key, 0) + prob
        # 归一化
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}
        return probs

    def predict_value(self, state: GameState) -> float:
        """基于 evaluate 的价值估计"""
        score = evaluate(state)
        return max(-1.0, min(1.0, score / 100.0))


class PUCTNode:
    """PUCT 搜索树节点"""
    __slots__ = (
        "state", "move", "parent", "children",
        "visits", "total_score", "prior", "depth", "is_terminal",
        "untried_moves", "untried_priors",
    )

    def __init__(
        self,
        state: GameState,
        move: Optional[Move] = None,
        parent: Optional[PUCTNode] = None,
        prior: float = 0.0,
        depth: int = 0,
        is_terminal: bool = False,
    ):
        self.state = state
        self.move = move
        self.parent = parent
        self.children: list[PUCTNode] = []
        self.visits = 0
        self.total_score = 0.0
        self.prior = prior
        self.depth = depth
        self.is_terminal = is_terminal
        self.untried_moves: list[Move] = []
        self.untried_priors: list[float] = []

    @property
    def q_value(self) -> float:
        return self.total_score / self.visits if self.visits > 0 else 0.0

    def puct_score(self, child: PUCTNode, c_puct: float = 1.5) -> float:
        """PUCT 评分公式"""
        if child.visits == 0:
            q = 0.0
        else:
            q = child.total_score / child.visits / 100.0  # 归一化到 [-1, 1]
        exploration = c_puct * child.prior * math.sqrt(self.visits) / (1 + child.visits)
        return q + exploration

    def best_child_puct(self, c_puct: float = 1.5) -> Optional[PUCTNode]:
        if not self.children:
            return None
        return max(self.children, key=lambda c: self.puct_score(c, c_puct))


class PUCTStrategy:
    """
    PUCT 搜索策略 — AlphaZero 风格

    与标准 MCTS 的关键区别：
    1. 使用 PUCT 公式替代 UCB1（先验概率引导搜索）
    2. 使用 Value Network 替代 rollout（直接评估叶节点）
    3. 支持 Dirichlet 噪声（根节点探索增强）
    4. 支持温度控制（动作选择的探索-利用平衡）

    用法::

        # 使用启发式先验（无需训练网络）
        strategy = PUCTStrategy(iterations=1000)

        # 使用训练好的神经网络
        strategy = PUCTStrategy(network=my_network, iterations=1000)
    """

    def __init__(
        self,
        *,
        network: Optional[PolicyValueNetwork] = None,
        iterations: int = 1000,
        time_limit: float = 1.0,
        c_puct: float = 1.5,
        dirichlet_alpha: float = 0.3,
        dirichlet_weight: float = 0.25,
        temperature: float = 1.0,
        use_value_network: bool = True,
        rollout_fallback_depth: int = 15,
        label: str = "puct",
    ):
        self._network = network or HeuristicPolicyValue()
        self._iterations = iterations
        self._time_limit = time_limit
        self._c_puct = c_puct
        self._dirichlet_alpha = dirichlet_alpha
        self._dirichlet_weight = dirichlet_weight
        self._temperature = temperature
        self._use_value_network = use_value_network
        self._rollout_fallback_depth = rollout_fallback_depth
        self._label = label
        self._rng = random.Random(42)

        # 运行时统计
        self._last_iterations = 0
        self._last_tree_size = 0

    @property
    def name(self) -> str:
        return self._label

    @property
    def last_iterations(self) -> int:
        return self._last_iterations

    @property
    def last_tree_size(self) -> int:
        return self._last_tree_size

    def choose(self, state: GameState, rules: Rules) -> Optional[Move]:
        if rules.is_terminal(state).value > 0:
            return None
        moves = rules.legal_moves(state)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        # 获取先验概率
        prior_probs = self._network.predict_policy(state)

        # 构建根节点
        root = PUCTNode(state=state, depth=0)
        root.untried_moves = list(moves)
        root.untried_priors = [
            prior_probs.get((m.src_col, m.dst_col), 1.0 / len(moves))
            for m in moves
        ]

        # 添加 Dirichlet 噪声到根节点先验
        if len(root.untried_priors) > 1:
            noise = self._dirichlet_noise(len(root.untried_priors))
            root.untried_priors = [
                (1 - self._dirichlet_weight) * p + self._dirichlet_weight * n
                for p, n in zip(root.untried_priors, noise)
            ]

        # PUCT 搜索
        t0 = time.perf_counter()
        iterations = 0

        for _ in range(self._iterations):
            if time.perf_counter() - t0 > self._time_limit:
                break

            # Selection
            node = root
            while node.children and not node.untried_moves:
                best = node.best_child_puct(self._c_puct)
                if best is None:
                    break
                node = best

            # Expansion
            if node.untried_moves and not node.is_terminal:
                idx = self._select_by_prior(node.untried_priors)
                move = node.untried_moves.pop(idx)
                prior = node.untried_priors.pop(idx)
                new_state = rules.apply_move(node.state, move)
                is_terminal = rules.is_terminal(new_state).value > 0

                child = PUCTNode(
                    state=new_state,
                    move=move,
                    parent=node,
                    prior=prior,
                    depth=node.depth + 1,
                    is_terminal=is_terminal,
                )

                if not is_terminal:
                    child_priors = self._network.predict_policy(new_state)
                    child_moves = rules.legal_moves(new_state)
                    child.untried_moves = list(child_moves)
                    child.untried_priors = [
                        child_priors.get((m.src_col, m.dst_col), 1.0 / max(1, len(child_moves)))
                        for m in child_moves
                    ]

                node.children.append(child)
                node = child

            # Evaluation
            if node.is_terminal:
                outcome = rules.is_terminal(node.state)
                from src.core.types import Outcome
                score = 100.0 if outcome == Outcome.WIN else -50.0
            elif self._use_value_network:
                score = self._network.predict_value(node.state) * 100.0
            else:
                score = self._quick_rollout(node.state, rules)

            # Backpropagation
            current = node
            while current is not None:
                current.visits += 1
                current.total_score += score
                current = current.parent

            iterations += 1

        self._last_iterations = iterations
        self._last_tree_size = self._count_nodes(root)

        # 选择最佳移动（温度控制）
        return self._select_final_move(root, rules)

    def _select_final_move(self, root: PUCTNode, rules: Rules) -> Move:
        """根据温度参数选择最终移动"""
        if not root.children:
            moves = rules.legal_moves(root.state)
            return moves[0] if moves else None

        if self._temperature < 0.01:
            # 温度趋近 0：纯贪心
            best = max(root.children, key=lambda c: c.visits)
            return best.move

        # 温度 > 0：按 visits^(1/τ) 采样
        visits = [c.visits for c in root.children]
        if self._temperature == 1.0:
            probs = [v / sum(visits) for v in visits]
        else:
            adjusted = [v ** (1.0 / self._temperature) for v in visits]
            total = sum(adjusted)
            probs = [a / total for a in adjusted]

        r = self._rng.random()
        cumulative = 0.0
        for child, prob in zip(root.children, probs):
            cumulative += prob
            if r <= cumulative:
                return child.move
        return root.children[-1].move

    def _select_by_prior(self, priors: list[float]) -> int:
        """按先验概率选择"""
        total = sum(priors)
        if total <= 0:
            return 0
        r = self._rng.random() * total
        cumulative = 0.0
        for i, p in enumerate(priors):
            cumulative += p
            if r <= cumulative:
                return i
        return len(priors) - 1

    def _dirichlet_noise(self, size: int) -> list[float]:
        """生成 Dirichlet 噪声"""
        samples = [self._rng.gammavariate(self._dirichlet_alpha, 1.0) for _ in range(size)]
        total = sum(samples)
        return [s / total if total > 0 else 1.0 / size for s in samples]

    def _quick_rollout(self, state: GameState, rules: Rules) -> float:
        """快速 rollout（作为 Value Network 的降级方案）"""
        from src.strategy.heuristics import heuristic_rollout
        return heuristic_rollout(
            state, rules,
            max_depth=self._rollout_fallback_depth,
            rng=self._rng,
        )

    def _count_nodes(self, node: PUCTNode) -> int:
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count


def create_puct(
    iterations: int = 1000,
    network: Optional[PolicyValueNetwork] = None,
    **kwargs,
) -> PUCTStrategy:
    """工厂函数：创建 PUCT 策略"""
    return PUCTStrategy(iterations=iterations, network=network, **kwargs)
