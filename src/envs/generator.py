"""
随机牌局生成器
设计原则：种子可控、可复现、与 Environment 协议解耦
"""

from __future__ import annotations

import random
from typing import Optional

from src.core.types import Card, CardFace, Column, GameState, Rank, Suit


def generate_game(seed: int = 0, difficulty: int = 2) -> GameState:
    """
    生成一个标准蜘蛛纸牌开局

    布局规则：
    - 前 4 列各 6 张牌（最上面 1 张明牌），共 24 张
    - 后 6 列各 5 张牌（最上面 1 张明牌），共 30 张
    - 初始发牌共 54 张明/暗牌
    - 发牌堆 50 张（5 批 × 10 张），用 5 个 Card token 表示

    Args:
        seed: 随机种子，0 表示随机
        difficulty: 花色数 1/2/4

    Returns:
        完整的初始 GameState
    """
    rng = random.Random(seed if seed != 0 else None)
    actual_seed = seed if seed != 0 else rng.randint(1, 2**31)

    # 生成牌组
    deck = _create_deck(difficulty, random.Random(actual_seed))
    rng.shuffle(deck)

    # 分配到 10 列
    columns: list[Column] = []
    idx = 0
    for col_idx in range(10):
        count = 6 if col_idx < 4 else 5
        cards = deck[idx : idx + count]
        idx += count
        # 最后一张明牌，其余暗牌
        cards[-1] = Card(suit=cards[-1].suit, rank=cards[-1].rank, face=CardFace.FACE_UP)
        for j in range(len(cards) - 1):
            cards[j] = Card(suit=cards[j].suit, rank=cards[j].rank, face=CardFace.FACE_DOWN)
        columns.append(Column(cards=tuple(cards)))

    # 发牌堆：5 个 token（每 token 代表一批 10 张）
    stock = tuple(
        Card(suit=Suit(i % 4), rank=Rank((i % 13) + 1), face=CardFace.FACE_UP)
        for i in range(5)
    )

    return GameState(
        columns=tuple(columns),
        stock=stock,
        completed=0,
        difficulty=difficulty,
        move_count=0,
        seed=actual_seed,
    )


def generate_batch(
    count: int,
    difficulty: int = 2,
    seed_start: int = 1,
) -> list[GameState]:
    """批量生成多局牌"""
    return [generate_game(seed=s, difficulty=difficulty) for s in range(seed_start, seed_start + count)]


def _create_deck(difficulty: int, rng: random.Random) -> list[Card]:
    """
    创建蜘蛛纸牌牌组（104 张）

    - 1花色: 8副♠ (104张♠)
    - 2花色: 4副♠ + 4副♥ (各52张)
    - 4花色: 2副♠ + 2副♥ + 2副♦ + 2副♣ (各26张)
    """
    deck: list[Card] = []
    if difficulty == 1:
        for _ in range(8):
            for r in Rank:
                deck.append(Card(suit=Suit.SPADE, rank=r, face=CardFace.FACE_DOWN))
    elif difficulty == 2:
        for _ in range(4):
            for r in Rank:
                deck.append(Card(suit=Suit.SPADE, rank=r, face=CardFace.FACE_DOWN))
                deck.append(Card(suit=Suit.HEART, rank=r, face=CardFace.FACE_DOWN))
    else:  # 4
        for _ in range(2):
            for s in Suit:
                for r in Rank:
                    deck.append(Card(suit=s, rank=r, face=CardFace.FACE_DOWN))

    assert len(deck) == 104, f"Deck should have 104 cards, got {len(deck)}"
    rng.shuffle(deck)
    return deck
