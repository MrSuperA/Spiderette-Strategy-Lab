"""
Gym 风格的 RL 环境包装器 — 将 GameSession 包装为标准 RL 接口
设计原则：兼容 Gym API（reset/step/observation_space），同时保持零外部依赖
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from src.core.rules import RulesEngine
from src.core.session import GameSession
from src.core.types import GameState, Move, Outcome
from src.envs.generator import generate_game
from src.envs.simulator import SimulatorEnv
from src.utils.logging import get_logger
_logger = get_logger(__name__)


@dataclass
class StepResult:
    """Gym 风格的 step 返回值"""
    observation: GameState
    reward: float
    terminated: bool
    truncated: bool
    info: dict


class SpideretteEnv:
    """
    Gym 风格的蜘蛛纸牌环境

    用法::

        env = SpideretteEnv(difficulty=1)
        obs, info = env.reset(seed=42)
        for _ in range(500):
            action = agent.select_action(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
    """

    def __init__(
        self,
        difficulty: int = 1,
        max_moves: int = 500,
        reward_config: Optional[dict] = None,
    ):
        self._difficulty = difficulty
        self._max_moves = max_moves
        self._rules = RulesEngine()
        self._env: Optional[SimulatorEnv] = None
        self._state: Optional[GameState] = None
        self._prev_state: Optional[GameState] = None
        self._step_count = 0
        self._reward_config = reward_config or {}

    @property
    def difficulty(self) -> int:
        return self._difficulty

    @property
    def rules(self) -> RulesEngine:
        return self._rules

    def reset(self, seed: Optional[int] = None) -> tuple[GameState, dict]:
        """重置环境，返回初始状态"""
        if seed is not None:
            self._env = SimulatorEnv(seed=seed, difficulty=self._difficulty)
        else:
            self._env = SimulatorEnv(
                seed=random.randint(1, 2**31),
                difficulty=self._difficulty,
            )
        self._state = self._env.observe()
        self._prev_state = None
        self._step_count = 0
        return self._state, {"seed": self._env._seed}

    def step(self, action: Optional[Move]) -> StepResult:
        """执行一步，返回 (obs, reward, terminated, truncated, info)"""
        if self._env is None or self._state is None:
            raise RuntimeError("环境未初始化，请先调用 reset()")

        self._prev_state = self._state
        prev_completed = self._state.completed
        prev_face_down = sum(c.face_down_count for c in self._state.columns)

        # 执行动作
        if action is None:
            # 策略无法行动 — 尝试发牌
            if self._rules.can_deal(self._state):
                success = self._env.deal()
            else:
                # 无法发牌也无合法移动 — 死局
                success = False
        elif action.is_deal:
            success = self._env.deal()
        else:
            success = self._env.step(action)

        self._state = self._env.observe()
        self._step_count += 1

        # 计算奖励
        reward = self._compute_reward(
            self._prev_state, self._state, action, prev_completed, prev_face_down
        )

        # 终止条件
        outcome = self._rules.is_terminal(self._state)
        terminated = outcome.value > 0
        truncated = self._step_count >= self._max_moves

        info = {
            "step": self._step_count,
            "outcome": outcome.name.lower() if terminated else "playing",
            "completed": self._state.completed,
            "success": success,
        }

        return StepResult(
            observation=self._state,
            reward=reward,
            terminated=terminated,
            truncated=truncated,
            info=info,
        )

    def action_space(self) -> list[Move]:
        """获取当前合法动作"""
        if self._state is None:
            return []
        return self._rules.legal_moves(self._state)

    def is_terminal(self) -> bool:
        """检查当前状态是否为终态（包括达到步数上限）"""
        if self._state is None:
            return True
        if self._step_count >= self._max_moves:
            return True
        outcome = self._rules.is_terminal(self._state)
        return outcome.value > 0

    def _compute_reward(
        self,
        prev: GameState,
        curr: GameState,
        action: Move,
        prev_completed: int,
        prev_face_down: int,
    ) -> float:
        """计算步级奖励"""
        reward = 0.0

        # 1. 完成序列（最高奖励）
        new_completed = curr.completed - prev_completed
        if new_completed > 0:
            reward += new_completed * 13.0

        # 2. 翻暗牌（信息获取）
        curr_face_down = sum(c.face_down_count for c in curr.columns)
        flipped = prev_face_down - curr_face_down
        if flipped > 0:
            reward += flipped * 1.0

        # 3. 同花色构建
        from src.strategy.heuristics import evaluate
        prev_score = evaluate(prev)
        curr_score = evaluate(curr)
        reward += (curr_score - prev_score) * 0.01

        # 4. 空列变化
        prev_empty = prev.empty_columns
        curr_empty = curr.empty_columns
        reward += (curr_empty - prev_empty) * 0.5

        # 5. 终局奖励
        outcome = self._rules.is_terminal(curr)
        if outcome == Outcome.WIN:
            reward += 100.0
        elif outcome == Outcome.DEADLOCK:
            reward -= 30.0

        # 6. 步数惩罚（鼓励效率）
        reward -= 0.1

        return reward

    def render(self) -> str:
        """返回当前状态的文本表示"""
        if self._state is None:
            return "未初始化"
        lines = [f"步数: {self._step_count}  完成: {self._state.completed}/8"]
        for i, col in enumerate(self._state.columns):
            cards = [f"{'?' if c.face.name=='FACE_DOWN' else str(c)}" for c in col.cards]
            lines.append(f"  列{i+1}: {' '.join(cards)}")
        return "\n".join(lines)
