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
from src.core.rules import COLUMN_COUNT
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
    带约束采样：优先分配与上方明牌兼容的牌，提高采样有效性。

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

    # 约束采样：为每列找到上方明牌的 rank 约束
    # 暗牌必须 rank < 上方最近明牌的 rank（降序排列规则）
    column_upper_bounds: list[Optional[int]] = []
    for col in state.columns:
        upper = None
        for card in col.cards:
            if card.face == CardFace.FACE_UP:
                upper = int(card.rank)
                break
        column_upper_bounds.append(upper)

    # 按约束强度排序列：有约束的列优先分配（更难满足）
    col_order = list(range(COLUMN_COUNT))
    col_order.sort(key=lambda ci: 0 if column_upper_bounds[ci] is not None else 1)

    # 为每列的暗牌分配牌
    assigned: list[list[tuple[Suit, Rank]]] = [[] for _ in range(COLUMN_COUNT)]
    pool = list(unknown_pool)

    for ci in col_order:
        col = state.columns[ci]
        n_fd = col.face_down_count
        if n_fd == 0:
            continue
        upper = column_upper_bounds[ci]

        # 从池中筛选满足约束的牌
        if upper is not None:
            candidates = [(s, r) for s, r in pool if int(r) < upper]
        else:
            candidates = list(pool)

        # 如果候选不足，回退到全池
        if len(candidates) < n_fd:
            candidates = list(pool)

        rng.shuffle(candidates)
        chosen = candidates[:n_fd]
        assigned[ci] = chosen

        # 从池中移除已分配的牌（用集合标记避免重复移除问题）
        chosen_set = set()
        for c in chosen:
            # 找到第一个未被标记的匹配项
            for idx, p in enumerate(pool):
                if idx not in chosen_set and p == c:
                    chosen_set.add(idx)
                    break
        pool = [p for idx, p in enumerate(pool) if idx not in chosen_set]

    # 构建新列
    new_columns = []
    fd_counters = [0] * COLUMN_COUNT
    for ci, col in enumerate(state.columns):
        new_cards = []
        for card in col.cards:
            if card.face == CardFace.FACE_DOWN:
                s, r = assigned[ci][fd_counters[ci]]
                new_cards.append(Card(suit=s, rank=r, face=CardFace.FACE_DOWN))
                fd_counters[ci] += 1
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
