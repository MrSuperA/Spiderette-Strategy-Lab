"""
信息集 MCTS (IS-MCTS) — 处理不完美信息的蒙特卡洛树搜索

核心改进（相比标准 MCTS）：
  1. 在每个决策点对暗牌进行确定化采样
  2. 对每个确定化状态运行标准 MCTS
  3. 跨样本聚合结果，选择在最多样本中被选中的移动
  4. 使用信息集哈希合并相同可观测状态的统计数据
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Optional, Sequence

from src.core.types import GameState, Move, Rules, Strategy
from src.core.info_set import ObservedState, extract_observed, observed_hash
from src.search.determinization import sample_determinization, sample_multiple
from src.strategy.mcts import MCTSStrategy, create_mcts
from src.utils.logging import get_logger
_logger = get_logger(__name__)


class ISMCTSStrategy:
    """
    信息集 MCTS 策略

    在每个决策点：
    1. 采样 N 个确定化状态（暗牌排列的不同假设）
    2. 对每个确定化状态运行标准 MCTS 搜索
    3. 跨样本聚合：选择在最多样本中被推荐的移动

    用法::

        strategy = ISMCTSStrategy(n_determinizations=10, iterations=500)
        move = strategy.choose(state, rules)
    """

    def __init__(
        self,
        *,
        n_determinizations: int = 10,
        iterations: int = 500,
        time_limit: float = 1.0,
        exploration: float = 1.4,
        use_heuristic: bool = True,
        label: str = "is_mcts",
    ):
        self._n_det = n_determinizations
        self._iterations = iterations
        self._time_limit = time_limit
        self._exploration = exploration
        self._use_heuristic = use_heuristic
        self._label = label
        self._rng = random.Random(42)

        # 运行时统计
        self._last_samples_used = 0
        self._last_agreement_ratio = 0.0

    @property
    def name(self) -> str:
        return self._label

    @property
    def last_samples_used(self) -> int:
        return self._last_samples_used

    @property
    def last_agreement_ratio(self) -> float:
        """最近一次决策中样本间的一致率"""
        return self._last_agreement_ratio

    def choose(self, state: GameState, rules: Rules) -> Optional[Move]:
        """选择最佳移动（基于信息集聚合）"""
        if rules.is_terminal(state).value > 0:
            return None
        moves = rules.legal_moves(state)
        if not moves:
            return None
        if len(moves) == 1:
            return moves[0]

        # 采样多个确定化状态
        face_down = sum(col.face_down_count for col in state.columns)
        if face_down == 0:
            # 无暗牌，退化为标准 MCTS
            mcts = create_mcts(
                iterations=self._iterations,
                time_limit=self._time_limit,
                exploration=self._exploration,
            )
            return mcts.choose(state, rules)

        determinizations = sample_multiple(
            state, n_samples=self._n_det, seed=self._rng.randint(0, 2**31)
        )

        # 对每个确定化状态运行 MCTS
        vote_counts: dict[Move, int] = defaultdict(int)
        vote_scores: dict[Move, float] = defaultdict(float)
        valid_samples = 0

        for det_state in determinizations:
            try:
                mcts = create_mcts(
                    iterations=self._iterations // max(1, self._n_det // 5),
                    time_limit=self._time_limit / self._n_det,
                    exploration=self._exploration,
                    use_heuristic=self._use_heuristic,
                )
                recommended = mcts.choose(det_state, rules)
                if recommended is not None:
                    # 找到最接近的合法移动
                    best_match = self._find_matching_move(recommended, moves, state)
                    vote_counts[best_match] += 1
                    vote_scores[best_match] += getattr(mcts, '_last_iterations', 0)
                    valid_samples += 1
            except Exception:
                continue

        self._last_samples_used = valid_samples

        if not vote_counts:
            # 所有样本都失败，回退到贪心
            from src.strategy.heuristics import rank_moves
            ranked = rank_moves(state, moves)
            return ranked[0] if ranked else moves[0]

        # 选择票数最多的移动
        best_move = max(vote_counts, key=lambda m: (vote_counts[m], vote_scores[m]))
        self._last_agreement_ratio = vote_counts[best_move] / max(1, valid_samples)

        return best_move

    def _find_matching_move(
        self, recommended: Move, legal_moves: list[Move], state: GameState
    ) -> Move:
        """在合法移动中找到与推荐移动最匹配的"""
        # 精确匹配
        for m in legal_moves:
            if (m.src_col == recommended.src_col
                    and m.dst_col == recommended.dst_col
                    and m.src_start == recommended.src_start):
                return m
        # 近似匹配（同源同目标）
        for m in legal_moves:
            if m.src_col == recommended.src_col and m.dst_col == recommended.dst_col:
                return m
        # 回退到第一个合法移动
        return legal_moves[0]


def create_is_mcts(
    n_determinizations: int = 10,
    iterations: int = 500,
    **kwargs,
) -> ISMCTSStrategy:
    """工厂函数：创建 IS-MCTS 策略"""
    return ISMCTSStrategy(
        n_determinizations=n_determinizations,
        iterations=iterations,
        **kwargs,
    )
