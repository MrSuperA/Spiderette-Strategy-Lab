"""
GameSession — 可迭代的游戏循环
设计原则：消除 MainController 和 ExperimentRunner 中重复的游戏循环
调用方通过迭代器协议控制节奏（日志/可视化/统计/中断）
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional, Sequence

from src.core.types import GameState, Move, Outcome, Rules, Strategy, Environment
from src.utils.logging import get_logger
_logger = get_logger(__name__)


@dataclass(slots=True)
class StepRecord:
    """每一步的完整快照 — 实验分析的原子数据单元"""
    state: GameState
    move: Optional[Move]
    strategy_name: str
    elapsed_ms: float
    legal_move_count: int
    step_index: int

    def to_dict(self) -> dict:
        return {
            "step": self.step_index,
            "move": self.move.to_dict() if self.move else None,
            "strategy": self.strategy_name,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "legal_moves": self.legal_move_count,
            "state": self.state.to_dict(),
        }


@dataclass(slots=True)
class GameResult:
    """一局完整结果"""
    outcome: Outcome
    steps: list[StepRecord] = field(default_factory=list)
    total_moves: int = 0
    total_time_ms: float = 0.0
    seed: int = 0
    completed: int = 0

    @property
    def is_win(self) -> bool:
        return self.outcome == Outcome.WIN

    @property
    def avg_step_ms(self) -> float:
        return self.total_time_ms / max(1, self.total_moves)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.name.lower(),
            "total_moves": self.total_moves,
            "total_time_ms": round(self.total_time_ms, 2),
            "avg_step_ms": round(self.avg_step_ms, 2),
            "seed": self.seed,
            "completed": self.completed,
        }


class GameSession:
    """
    核心抽象：一个游戏会话就是可迭代的步进序列。

    用法::

        # 自动运行到底
        result = GameSession(env, strategy).run()

        # 逐步控制
        for step in GameSession(env, strategy):
            print(step)

        # 带回调的运行
        session = GameSession(env, strategy, on_step=lambda s: print(s.step_index))
        result = session.run()
    """

    CYCLE_WINDOW = 20  # 检测最近 N 步的状态重复

    def __init__(
        self,
        env: Environment,
        strategy: Strategy,
        *,
        max_moves: int = 500,
        on_step: Optional[callable] = None,
        step_delay: float = 0.0,
    ):
        self.env = env
        self.strategy = strategy
        self.rules = env.rules
        self.max_moves = max_moves
        self.on_step = on_step
        self.step_delay = step_delay  # 每步最小间隔（秒），0=不限速
        self._step_count = 0

    def __iter__(self) -> Iterator[StepRecord]:
        """每次 yield 一步，调用方决定如何处理"""
        self._step_count = 0
        recent_hashes: list[int] = []
        recent_moves: list[Optional[Move]] = []
        cycle_strikes = 0

        # 进展追踪
        last_progress_step = 0
        last_completed = 0
        last_face_down = sum(c.face_down_count for c in self.env.observe().columns)
        PROGRESS_WINDOW = 40  # 40步无进展触发恢复

        for i in range(self.max_moves):
            if self.env.done():
                break

            state = self.env.observe()
            legal_moves = self.rules.legal_moves(state)

            # 循环检测：位置哈希
            pos_hash = hash((state.columns, state.stock, state.completed))
            if pos_hash in recent_hashes:
                cycle_strikes += 1
            else:
                cycle_strikes = 0
            recent_hashes.append(pos_hash)
            if len(recent_hashes) > self.CYCLE_WINDOW:
                recent_hashes.pop(0)

            # 进展检测：完成数或暗牌数是否变化
            cur_completed = state.completed
            cur_face_down = sum(c.face_down_count for c in state.columns)
            if cur_completed > last_completed or cur_face_down < last_face_down:
                last_progress_step = self._step_count
                last_completed = cur_completed
                last_face_down = cur_face_down

            # 策略决策
            t0 = time.perf_counter()
            move = self.strategy.choose(state, self.rules)
            elapsed = (time.perf_counter() - t0) * 1000

            # 循环恢复
            if cycle_strikes >= 3:
                if self.rules.can_deal(state):
                    move = None
                    cycle_strikes = 0
                elif legal_moves:
                    alt_moves = [m for m in legal_moves if m not in recent_moves[-6:]]
                    if not alt_moves:
                        alt_moves = list(legal_moves)
                    move = random.choice(alt_moves)
                    cycle_strikes = 0

            # 无进展恢复：40步内无新完成/无新翻牌 → 强制发牌或随机
            steps_since_progress = self._step_count - last_progress_step
            if steps_since_progress >= PROGRESS_WINDOW and self._step_count > 0:
                if self.rules.can_deal(state):
                    move = None  # 强制发牌
                    last_progress_step = self._step_count  # 重置计数
                elif legal_moves:
                    # 排除最近频繁使用的移动
                    alt_moves = [m for m in legal_moves if m not in recent_moves[-10:]]
                    if not alt_moves:
                        alt_moves = list(legal_moves)
                    move = random.choice(alt_moves)
                    last_progress_step = self._step_count

            recent_moves.append(move)
            if len(recent_moves) > 20:
                recent_moves.pop(0)

            # 执行
            if move is None:
                if self.rules.can_deal(state):
                    self.env.deal()
                else:
                    if not legal_moves:
                        break
                    move = random.choice(legal_moves)
                    self.env.step(move)
            else:
                self.env.step(move)

            self._step_count += 1
            record = StepRecord(
                state=state,
                move=move,
                strategy_name=self.strategy.name,
                elapsed_ms=elapsed,
                legal_move_count=len(legal_moves),
                step_index=self._step_count,
            )

            if self.on_step:
                self.on_step(record)

            # 步间限速：确保每步至少间隔 step_delay 秒
            if self.step_delay > 0:
                elapsed_s = elapsed / 1000
                if elapsed_s < self.step_delay:
                    time.sleep(self.step_delay - elapsed_s)

            yield record

    def run(self) -> GameResult:
        """消费迭代器，收集完整结果"""
        t0 = time.perf_counter()
        steps: list[StepRecord] = []
        for step in self:
            steps.append(step)
        total_ms = (time.perf_counter() - t0) * 1000

        final = self.env.observe()
        outcome = self.rules.is_terminal(final)

        # 达到步数上限但未结束 → 视为死局
        if outcome == Outcome.PLAYING and len(steps) >= self.max_moves:
            outcome = Outcome.DEADLOCK

        return GameResult(
            outcome=outcome,
            steps=steps,
            total_moves=len(steps),
            total_time_ms=total_ms,
            seed=final.seed,
            completed=final.completed,
        )
