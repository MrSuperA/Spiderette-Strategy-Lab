"""
模拟器环境 — 内置纯模拟，满足 Environment 协议
设计原则：种子可控、可复现、不依赖外部进程
"""

from __future__ import annotations

import random
from typing import Optional

from src.core.types import Card, CardFace, Column, GameState, Move, Suit
from src.core.rules import RulesEngine
from src.envs.generator import generate_game


class SimulatorEnv:
    """
    模拟器游戏环境（满足 Environment 协议）
    在纯 Python 中模拟完整蜘蛛纸牌流程，无需真实游戏
    """

    def __init__(self, seed: int = 0, difficulty: int = 2):
        self._seed = seed
        self._difficulty = difficulty
        self._state = generate_game(seed=seed, difficulty=difficulty)
        self._rules = RulesEngine()
        self._history: list[GameState] = [self._state]

    @property
    def rules(self) -> RulesEngine:
        return self._rules

    @property
    def history(self) -> list[GameState]:
        return self._history

    def observe(self) -> GameState:
        return self._state

    def step(self, move: Move) -> bool:
        """执行移牌"""
        if self.done():
            return False
        try:
            self._state = self._rules.apply_move(self._state, move)
            self._history.append(self._state)
            return True
        except Exception:
            return False

    def deal(self) -> bool:
        """发牌"""
        if not self._rules.can_deal(self._state):
            return False
        self._state = self._rules.deal(self._state)
        self._history.append(self._state)
        return True

    def reset(self, seed: int = 0) -> bool:
        """重置到新牌局"""
        if seed:
            self._seed = seed
        self._state = generate_game(seed=self._seed, difficulty=self._difficulty)
        self._history = [self._state]
        return True

    def done(self) -> bool:
        return self._rules.is_terminal(self._state).value > 0


def create_env(seed: int = 0, difficulty: int = 2) -> SimulatorEnv:
    """工厂函数 — 满足 entry_points 注册约定"""
    return SimulatorEnv(seed=seed, difficulty=difficulty)
