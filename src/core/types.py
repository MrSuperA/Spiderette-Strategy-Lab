"""
核心类型定义 — 数据模型 + 协议接口
设计原则：不可变数据(frozen)、零外部依赖、Protocol 结构化子类型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import (
    Protocol,
    Optional,
    Sequence,
    runtime_checkable,
)


# ═══════════════════════════════════════════════════
#  枚举
# ═══════════════════════════════════════════════════

class Suit(IntEnum):
    """花色（0-3）"""
    SPADE = 0
    HEART = 1
    DIAMOND = 2
    CLUB = 3

    @property
    def symbol(self) -> str:
        return {0: "♠", 1: "♥", 2: "♦", 3: "♣"}[self.value]

    @property
    def is_red(self) -> bool:
        return self.value in (1, 2)

    def __str__(self) -> str:
        return self.symbol


_RANK_LABELS: dict[int, str] = {
    1: "A", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7",
    8: "8", 9: "9", 10: "10", 11: "J", 12: "Q", 13: "K",
}


class Rank(IntEnum):
    """点数（1-13，A=1, K=13）"""
    A = 1
    _2 = 2
    _3 = 3
    _4 = 4
    _5 = 5
    _6 = 6
    _7 = 7
    _8 = 8
    _9 = 9
    _10 = 10
    J = 11
    Q = 12
    K = 13

    def __str__(self) -> str:
        return _RANK_LABELS.get(self.value, str(self.value))


class CardFace(IntEnum):
    """牌面朝向"""
    FACE_DOWN = 0
    FACE_UP = 1


class Difficulty(IntEnum):
    """难度（花色数）"""
    ONE = 1
    TWO = 2
    FOUR = 4


class Outcome(IntEnum):
    """游戏结果"""
    PLAYING = 0
    WIN = 1
    DEADLOCK = 2


# ═══════════════════════════════════════════════════
#  数据模型（不可变、可哈希、可序列化）
# ═══════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class Card:
    """一张牌"""
    suit: Suit
    rank: Rank
    face: CardFace = CardFace.FACE_UP

    @property
    def face_up(self) -> bool:
        return self.face == CardFace.FACE_UP

    @property
    def color(self) -> str:
        return "red" if self.suit.is_red else "black"

    def __str__(self) -> str:
        if not self.face_up:
            return "??"
        return f"{self.suit}{self.rank}"

    def to_dict(self) -> dict:
        return {
            "suit": self.suit.symbol,
            "rank": str(self.rank),
            "red": self.suit.is_red,
            "face_up": self.face_up,
        }


@dataclass(frozen=True, slots=True)
class Column:
    """一列牌"""
    cards: tuple[Card, ...] = ()

    @property
    def length(self) -> int:
        return len(self.cards)

    @property
    def is_empty(self) -> bool:
        return len(self.cards) == 0

    @property
    def top_card(self) -> Optional[Card]:
        return self.cards[-1] if self.cards else None

    @property
    def face_up_count(self) -> int:
        return sum(1 for c in self.cards if c.face_up)

    @property
    def face_down_count(self) -> int:
        return sum(1 for c in self.cards if not c.face_up)

    def runnable_start(self) -> int:
        """可运行序列（同花色连续递减的明牌序列）的起始索引"""
        if not self.cards:
            return 0
        start = len(self.cards) - 1
        while start > 0:
            curr = self.cards[start]
            prev = self.cards[start - 1]
            if (prev.face_up
                    and curr.face_up
                    and prev.suit == curr.suit
                    and prev.rank == curr.rank + 1):
                start -= 1
            else:
                break
        return start

    def to_dict(self) -> dict:
        return {
            "length": self.length,
            "face_down": self.face_down_count,
            "face_up": [c.to_dict() for c in self.cards if c.face_up],
        }


@dataclass(frozen=True, slots=True)
class GameState:
    """
    牌局完整状态 — 纯数据，零副作用
    columns + stock + completed 构成完整可逆描述
    """
    columns: tuple[Column, ...]  # 10 列
    stock: tuple[tuple[Card, ...], ...]  # 发牌堆（5批，每批10张实际牌）
    completed: int = 0           # 已完成的同花色 K→A 序列数
    difficulty: int = 2
    move_count: int = 0
    seed: int = 0

    def __post_init__(self) -> None:
        if len(self.columns) != 10:
            raise ValueError(f"Expected 10 columns, got {len(self.columns)}")

    @property
    def total_cards(self) -> int:
        in_columns = sum(c.length for c in self.columns)
        return in_columns + sum(len(batch) for batch in self.stock) + self.completed * 13

    @property
    def empty_columns(self) -> int:
        return sum(1 for c in self.columns if c.is_empty)

    @property
    def remaining_deals(self) -> int:
        return len(self.stock)

    def to_dict(self) -> dict:
        return {
            "columns": [c.to_dict() for c in self.columns],
            "stock_remaining": self.remaining_deals,
            "completed": self.completed,
            "difficulty": self.difficulty,
            "move_count": self.move_count,
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class Move:
    """一个移动操作 — 策略与环境之间的唯一契约
    src_col + src_start + dst_col 完整描述一次移牌
    dst_col == -1 表示发牌操作
    """
    src_col: int
    src_start: int   # 序列中起始位置（从底开始的索引）
    dst_col: int     # -1 表示发牌
    card_count: int = 1

    def __post_init__(self) -> None:
        # 移牌时 card_count 自动计算
        if self.dst_col >= 0 and self.card_count <= 0:
            object.__setattr__(self, "card_count", 1)

    @property
    def is_deal(self) -> bool:
        return self.dst_col == -1

    def to_dict(self) -> dict:
        if self.is_deal:
            return {"action": "deal"}
        return {
            "action": "move",
            "src": self.src_col,
            "dst": self.dst_col,
            "start": self.src_start,
            "count": self.card_count,
        }


# ═══════════════════════════════════════════════════
#  协议接口（Protocol — 结构化子类型）
# ═══════════════════════════════════════════════════

@runtime_checkable
class Rules(Protocol):
    """规则引擎协议 — 纯函数集合，无状态无副作用"""

    def legal_moves(self, state: GameState) -> Sequence[Move]:
        """返回当前状态的所有合法移动"""
        ...

    def apply_move(self, state: GameState, move: Move) -> GameState:
        """执行移动，返回新状态（不修改原状态）"""
        ...

    def deal(self, state: GameState) -> GameState:
        """发牌，返回新状态"""
        ...

    def can_deal(self, state: GameState) -> bool:
        """是否可以发牌"""
        ...

    def is_win(self, state: GameState) -> bool:
        """是否胜利"""
        ...

    def is_deadlock(self, state: GameState) -> bool:
        """是否死局"""
        ...

    def is_terminal(self, state: GameState) -> Outcome:
        """游戏是否结束"""
        ...


@runtime_checkable
class Strategy(Protocol):
    """策略协议 — 给定状态，返回移动决策"""

    @property
    def name(self) -> str:
        """策略名称"""
        ...

    def choose(self, state: GameState, rules: Rules) -> Optional[Move]:
        """返回最佳移动，None 表示发牌或无解"""
        ...


@runtime_checkable
class Environment(Protocol):
    """游戏环境协议 — 提供状态 + 接受操作"""

    def observe(self) -> GameState:
        """获取当前状态"""
        ...

    def step(self, move: Move) -> bool:
        """执行移动，返回是否成功"""
        ...

    def deal(self) -> bool:
        """发牌，返回是否成功"""
        ...

    def reset(self, seed: int = 0) -> bool:
        """重置环境"""
        ...

    def done(self) -> bool:
        """游戏是否结束"""
        ...

    @property
    def rules(self) -> Rules:
        """环境绑定的规则引擎"""
        ...
