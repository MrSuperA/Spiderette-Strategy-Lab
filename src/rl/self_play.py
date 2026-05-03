"""
自博弈数据收集器 — 用 MCTS 搜索生成训练数据
参考 AlphaZero 的自博弈流程：MCTS 策略 → 对局 → (state, policy, value) 三元组
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from src.core.types import GameState, Move, Outcome
from src.core.rules import RulesEngine
from src.search.puct import PUCTStrategy, create_puct
from src.rl.environment import SpideretteEnv


@dataclass
class SelfPlaySample:
    """自博弈训练样本"""
    state: GameState
    policy: dict[tuple[int, int], float]  # (src_col, dst_col) → 概率
    outcome: float                         # 最终结果 (1.0=胜, -1.0=败, 0.0=平)

    def to_features_and_labels(self) -> tuple[list[float], dict, float]:
        """转换为训练数据"""
        from src.network.feature_v2 import extract_features_v2
        features = extract_features_v2(self.state)
        return features, self.policy, self.outcome


@dataclass
class SelfPlayResult:
    """一局自博弈结果"""
    samples: list[SelfPlaySample] = field(default_factory=list)
    outcome: str = "playing"
    total_moves: int = 0


class SelfPlayCollector:
    """
    自博弈数据收集器

    流程：
    1. 使用 PUCT/MCTS 策略玩游戏
    2. 在每个决策点记录 (state, mcts_policy, outcome)
    3. 收集训练数据用于更新神经网络

    用法::

        collector = SelfPlayCollector(strategy_name="puct")
        result = collector.play_one_game(seed=42, difficulty=1)
        features, policies, outcomes = collector.collect_training_data([result])
    """

    def __init__(
        self,
        strategy_name: str = "puct",
        temperature_schedule: Optional[dict] = None,
    ):
        self._strategy_name = strategy_name
        self._temp_schedule = temperature_schedule or {"early": 1.0, "late": 0.1, "threshold": 100}
        self._rules = RulesEngine()

    def play_one_game(
        self,
        seed: int,
        difficulty: int = 1,
        max_moves: int = 500,
    ) -> SelfPlayResult:
        """运行一局自博弈，收集训练数据"""
        env = SpideretteEnv(difficulty=difficulty, max_moves=max_moves)
        state, info = env.reset(seed=seed)

        # 创建搜索策略
        if self._strategy_name == "puct":
            strategy = create_puct(iterations=500)
        else:
            from src.strategy.registry import get_strategy
            strategy = get_strategy(self._strategy_name)

        result = SelfPlayResult()
        rules = self._rules

        for step in range(max_moves):
            if rules.is_terminal(state).value > 0:
                break

            # 获取搜索策略的推荐
            move = strategy.choose(state, rules)
            if move is None:
                break

            # 记录 MCTS 的策略分布（如果有）
            policy = self._extract_policy(state, strategy, rules)

            # 执行动作
            step_result = env.step(move)
            result.samples.append(SelfPlaySample(
                state=state,
                policy=policy,
                outcome=0.0,  # 后续填充
            ))

            state = step_result.observation
            result.total_moves += 1

            if step_result.terminated or step_result.truncated:
                break

        # 填充 outcome
        final_outcome = rules.is_terminal(state)
        if final_outcome == Outcome.WIN:
            outcome_val = 1.0
            result.outcome = "win"
        elif final_outcome == Outcome.DEADLOCK:
            outcome_val = -1.0
            result.outcome = "deadlock"
        else:
            outcome_val = 0.0
            result.outcome = "timeout"

        # 为所有样本设置 outcome（可以考虑折扣因子）
        for sample in result.samples:
            sample.outcome = outcome_val

        return result

    def _extract_policy(
        self, state: GameState, strategy, rules: RulesEngine
    ) -> dict[tuple[int, int], float]:
        """从搜索策略中提取动作概率分布"""
        policy = {}
        moves = rules.legal_moves(state)
        if not moves:
            return policy

        # 如果策略有搜索树信息
        if hasattr(strategy, '_last_root') and strategy._last_root:
            root = strategy._last_root
            total_visits = root.visits
            if total_visits > 0:
                for child in root.children:
                    if child.move:
                        key = (child.move.src_col, child.move.dst_col)
                        policy[key] = child.visits / total_visits

        # 如果策略是 PUCT，从根节点提取
        if hasattr(strategy, '_last_root') and hasattr(strategy._last_root, 'children'):
            if not policy:
                from src.strategy.heuristics import rank_moves
                ranked = rank_moves(state, moves)
                for i, m in enumerate(ranked[:10]):
                    key = (m.src_col, m.dst_col)
                    policy[key] = max(0.01, 1.0 / (i + 1))

        # 归一化
        total = sum(policy.values())
        if total > 0:
            policy = {k: v / total for k, v in policy.items()}
        else:
            # 均匀分布
            for m in moves:
                key = (m.src_col, m.dst_col)
                policy[key] = 1.0 / len(moves)

        return policy

    def collect_training_data(
        self,
        results: list[SelfPlayResult],
    ) -> tuple[list[list[float]], list[dict], list[float]]:
        """
        从多局自博弈结果中收集训练数据

        Returns:
            (features_list, policies_list, outcomes_list)
        """
        features_list = []
        policies_list = []
        outcomes_list = []

        for result in results:
            for sample in result.samples:
                feat, policy, outcome = sample.to_features_and_labels()
                features_list.append(feat)
                policies_list.append(policy)
                outcomes_list.append(outcome)

        return features_list, policies_list, outcomes_list
