"""
信息集抽象 — 将不完美信息博弈的状态分为可观测和隐藏两部分
设计原则：
  - ObservedState: 玩家可见的信息（明牌、列结构、发牌堆剩余）
  - HiddenState: 暗牌实际内容（仅供模拟器内部使用）
  - InformationSet: 基于 ObservedState 的哈希，用于 IS-MCTS 节点标识
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.core.types import Card, CardFace, Column, GameState, Rank, Suit


@dataclass(frozen=True, slots=True)
class VisibleCard:
    """可见牌信息（只含明牌的 rank 和 suit）"""
    suit: Suit
    rank: Rank

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


@dataclass(frozen=True, slots=True)
class VisibleColumn:
    """列的可观测信息（只含明牌 + 暗牌数量）"""
    visible_cards: tuple[VisibleCard, ...]  # 从底到顶的明牌
    face_down_count: int                     # 暗牌数量

    @property
    def length(self) -> int:
        return len(self.visible_cards) + self.face_down_count

    @property
    def is_empty(self) -> bool:
        return self.length == 0

    @property
    def face_up_count(self) -> int:
        return len(self.visible_cards)


@dataclass(frozen=True, slots=True)
class ObservedState:
    """
    玩家可观测的状态 — 不包含暗牌的具体信息

    用于：
    1. 信息集哈希（IS-MCTS 节点标识）
    2. 策略的输入（不泄露暗牌信息）
    3. 特征提取（只基于可见信息）
    """
    columns: tuple[VisibleColumn, ...]  # 10 列的可见信息
    stock_remaining: int                 # 发牌堆剩余批数
    completed: int                       # 已完成序列数
    move_count: int                      # 总步数
    difficulty: int                      # 难度 (1/2/4)

    def to_game_state_hint(self) -> dict:
        """转换为不含暗牌信息的状态摘要"""
        return {
            "columns": [
                {
                    "visible_count": len(col.visible_cards),
                    "face_down_count": col.face_down_count,
                    "top_card": str(col.visible_cards[-1]) if col.visible_cards else None,
                }
                for col in self.columns
            ],
            "stock_remaining": self.stock_remaining,
            "completed": self.completed,
            "move_count": self.move_count,
            "difficulty": self.difficulty,
        }


def extract_observed(state: GameState) -> ObservedState:
    """从完整 GameState 提取可观测状态（隐藏暗牌信息）"""
    columns = []
    for col in state.columns:
        visible = []
        for card in col.cards:
            if card.face == CardFace.FACE_UP:
                visible.append(VisibleCard(suit=card.suit, rank=card.rank))
        columns.append(VisibleColumn(
            visible_cards=tuple(visible),
            face_down_count=col.face_down_count,
        ))
    return ObservedState(
        columns=tuple(columns),
        stock_remaining=state.remaining_deals,
        completed=state.completed,
        move_count=state.move_count,
        difficulty=state.difficulty,
    )


def observed_hash(state: ObservedState) -> int:
    """信息集哈希 — 只基于可观测信息"""
    parts = []
    for col in state.columns:
        parts.append(col.face_down_count)
        for card in col.visible_cards:
            parts.append(card.suit.value * 100 + card.rank.value)
    parts.append(state.stock_remaining)
    parts.append(state.completed)
    return hash(tuple(parts))
