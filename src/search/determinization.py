"""
暗牌确定化采样器 — 将不完美信息状态转换为多个确定化状态
用于 IS-MCTS 的预处理阶段

设计原则：
  1. 基于已知牌推断未知牌池
  2. 随机采样暗牌排列
  3. 生成完整的 GameState 供标准 MCTS 使用
  4. 支持加权采样（基于牌的先验概率）
"""

from __future__ import annotations

import random
from typing import Optional

from src.core.types import Card, CardFace, Column, GameState, Rank, Suit
from src.core.info_set import ObservedState, VisibleColumn


from collections import Counter


def collect_known_cards(state: GameState) -> Counter:
    """收集所有已知牌（明牌），使用 Counter 处理重复牌"""
    known: Counter = Counter()
    for col in state.columns:
        for card in col.cards:
            if card.face == CardFace.FACE_UP:
                known[(card.suit, card.rank)] += 1
    return known


def build_full_deck(difficulty: int) -> list[tuple[Suit, Rank]]:
    """构建完整牌组（104 张）"""
    deck: list[tuple[Suit, Rank]] = []
    if difficulty == 1:
        for _ in range(8):
            for r in Rank:
                deck.append((Suit.SPADE, r))
    elif difficulty == 2:
        for _ in range(4):
            for r in Rank:
                deck.append((Suit.SPADE, r))
                deck.append((Suit.HEART, r))
    else:  # 4
        for _ in range(2):
            for s in Suit:
                for r in Rank:
                    deck.append((s, r))
    return deck


def compute_unknown_pool(state: GameState) -> list[tuple[Suit, Rank]]:
    """计算未知牌池（104张 - 已知明牌）"""
    known = collect_known_cards(state)
    full_deck = build_full_deck(state.difficulty)
    remaining = Counter(full_deck)
    remaining.subtract(known)
    unknown = []
    for card, count in remaining.items():
        unknown.extend([card] * max(0, count))
    return unknown


def count_face_down_per_column(state: GameState) -> list[int]:
    """统计每列的暗牌数量"""
    return [col.face_down_count for col in state.columns]


def sample_determinization(
    state: GameState,
    rng: Optional[random.Random] = None,
) -> GameState:
    """
    采样一个确定化状态：将暗牌替换为随机排列的未知牌

    算法：
    1. 收集所有暗牌位置（每列的 face_down 部分）
    2. 从未知牌池中随机抽取等量的牌
    3. 将抽取的牌分配到暗牌位置
    4. 保持明牌不变，生成新的 GameState

    Args:
        state: 当前完整信息状态（模拟器内部使用）
        rng: 随机数生成器（可选，用于可复现采样）

    Returns:
        一个新的 GameState，暗牌被替换为采样的牌
    """
    if rng is None:
        rng = random.Random()

    unknown_pool = compute_unknown_pool(state)
    rng.shuffle(unknown_pool)

    total_face_down = sum(col.face_down_count for col in state.columns)
    if total_face_down == 0 or len(unknown_pool) < total_face_down:
        return state  # 无暗牌或牌池不足，直接返回

    sampled_cards = unknown_pool[:total_face_down]
    card_idx = 0

    new_columns = []
    for col in state.columns:
        new_cards = []
        for card in col.cards:
            if card.face == CardFace.FACE_DOWN:
                s, r = sampled_cards[card_idx]
                new_cards.append(Card(suit=s, rank=r, face=CardFace.FACE_DOWN))
                card_idx += 1
            else:
                new_cards.append(card)
        new_columns.append(Column(cards=tuple(new_cards)))

    return GameState(
        columns=tuple(new_columns),
        stock=state.stock,
        completed=state.completed,
        difficulty=state.difficulty,
        move_count=state.move_count,
        seed=state.seed,
    )


def sample_multiple(
    state: GameState,
    n_samples: int = 10,
    seed: int = 0,
) -> list[GameState]:
    """
    采样多个确定化状态

    Args:
        state: 当前状态
        n_samples: 采样数量
        seed: 基础种子（用于可复现）

    Returns:
        确定化状态列表
    """
    base_rng = random.Random(seed) if seed else random.Random()
    samples = []
    for i in range(n_samples):
        rng = random.Random(base_rng.randint(0, 2**31))
        samples.append(sample_determinization(state, rng))
    return samples


def estimate_face_down_distribution(state: GameState, n_samples: int = 100) -> dict:
    """
    估计暗牌的花色/点数分布

    Returns:
        {column_idx: {position: {suit: count, rank: count}}}
    """
    suit_counts: list[dict] = [{} for _ in range(10)]
    rank_counts: list[dict] = [{} for _ in range(10)]

    for _ in range(n_samples):
        det = sample_determinization(state)
        for ci, col in enumerate(det.columns):
            face_down = [c for c in col.cards if c.face == CardFace.FACE_DOWN]
            for pi, card in enumerate(face_down):
                key = f"pos_{pi}"
                if key not in suit_counts[ci]:
                    suit_counts[ci][key] = {s: 0 for s in Suit}
                    rank_counts[ci][key] = {r: 0 for r in Rank}
                suit_counts[ci][key][card.suit] += 1
                rank_counts[ci][key][card.rank] += 1

    return {"suit_counts": suit_counts, "rank_counts": rank_counts}
