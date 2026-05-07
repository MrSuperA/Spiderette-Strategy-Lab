"""
课程学习调度器 — 根据策略表现自适应调整训练难度
设计原则：从简单到复杂，避免在过难的任务上浪费训练资源
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CurriculumStage:
    """课程阶段"""
    difficulty: int           # 1/2/4 花色
    min_episodes: int         # 最少训练轮数
    promotion_threshold: float  # 晋级胜率阈值
    demotion_threshold: float   # 降级胜率阈值
    label: str = ""


# 默认课程阶段
DEFAULT_CURRICULUM = [
    CurriculumStage(difficulty=1, min_episodes=100, promotion_threshold=0.15, demotion_threshold=0.0, label="1花色入门"),
    CurriculumStage(difficulty=1, min_episodes=200, promotion_threshold=0.30, demotion_threshold=0.05, label="1花色进阶"),
    CurriculumStage(difficulty=1, min_episodes=300, promotion_threshold=0.50, demotion_threshold=0.20, label="1花色精通"),
    CurriculumStage(difficulty=2, min_episodes=200, promotion_threshold=0.15, demotion_threshold=0.0, label="2花色入门"),
    CurriculumStage(difficulty=2, min_episodes=300, promotion_threshold=0.30, demotion_threshold=0.05, label="2花色进阶"),
    CurriculumStage(difficulty=4, min_episodes=200, promotion_threshold=0.10, demotion_threshold=0.0, label="4花色入门"),
    CurriculumStage(difficulty=4, min_episodes=500, promotion_threshold=0.20, demotion_threshold=0.02, label="4花色进阶"),
]


class CurriculumScheduler:
    """
    课程学习调度器

    根据策略在当前阶段的表现，自动晋级到更难的阶段或降级到更简单的阶段。

    用法::

        scheduler = CurriculumScheduler()
        for episode in range(10000):
            difficulty = scheduler.get_difficulty()
            # ... 训练 ...
            scheduler.update(win_rate=recent_win_rate)
    """

    def __init__(
        self,
        curriculum: Optional[list[CurriculumStage]] = None,
        window_size: int = 100,
    ):
        self._curriculum = curriculum or DEFAULT_CURRICULUM
        self._stage_idx = 0
        self._window_size = window_size
        self._recent_results: deque[float] = deque(maxlen=window_size)
        self._stage_episodes = 0
        self._history: list[dict] = []

    @property
    def current_stage(self) -> CurriculumStage:
        return self._curriculum[self._stage_idx]

    @property
    def stage_index(self) -> int:
        return self._stage_idx

    @property
    def total_stages(self) -> int:
        return len(self._curriculum)

    def get_difficulty(self) -> int:
        """获取当前应使用的难度"""
        return self.current_stage.difficulty

    def get_label(self) -> str:
        """获取当前阶段标签"""
        return self.current_stage.label

    def update(self, win_rate: float) -> Optional[str]:
        """
        更新调度器状态

        Args:
            win_rate: 最近一个评估周期的胜率

        Returns:
            "promoted" / "demoted" / None
        """
        self._recent_results.append(win_rate)
        self._stage_episodes += 1

        stage = self.current_stage

        # 检查是否满足晋级条件
        if self._stage_episodes >= stage.min_episodes:
            avg_wr = self._average_win_rate()

            if avg_wr >= stage.promotion_threshold:
                return self._promote()
            elif avg_wr < stage.demotion_threshold and self._stage_idx > 0:
                return self._demote()

        return None

    def _promote(self) -> str:
        """晋级到下一阶段"""
        if self._stage_idx < len(self._curriculum) - 1:
            old_stage = self.current_stage
            self._stage_idx += 1
            self._stage_episodes = 0
            self._recent_results.clear()
            self._history.append({
                "action": "promote",
                "from": old_stage.label,
                "to": self.current_stage.label,
            })
            return "promoted"
        return "at_max"

    def _demote(self) -> str:
        """降级到上一阶段"""
        if self._stage_idx > 0:
            old_stage = self.current_stage
            self._stage_idx -= 1
            self._stage_episodes = 0
            self._recent_results.clear()
            self._history.append({
                "action": "demote",
                "from": old_stage.label,
                "to": self.current_stage.label,
            })
            return "demoted"
        return "at_min"

    def _average_win_rate(self) -> float:
        """计算近期平均胜率"""
        if not self._recent_results:
            return 0.0
        return sum(self._recent_results) / len(self._recent_results)

    def get_status(self) -> dict:
        """获取调度器状态摘要"""
        return {
            "stage": self._stage_idx,
            "stage_label": self.current_stage.label,
            "difficulty": self.current_stage.difficulty,
            "episodes_in_stage": self._stage_episodes,
            "min_episodes": self.current_stage.min_episodes,
            "recent_win_rate": self._average_win_rate(),
            "promotion_threshold": self.current_stage.promotion_threshold,
            "history": self._history[-5:],
        }
