"""
启发式评估函数集 — MCTS 的模拟与评估引导
设计原则：纯函数，无状态，所有评估逻辑集中管理
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Sequence

from src.core.types import Card, CardFace, Column, GameState, Move, Rank, Suit
from src.core.rules import COMPLETE_SEQ_LEN, COLUMN_COUNT


# ═══════════════════════════════════════════════════
#  评估维度常量
# ═══════════════════════════════════════════════════

_WEIGHTS = {
    "completed": 50.0,       # 已完成序列数（最高权重）
    "same_suit_seq": 9.0,    # 同花色连续序列（合并了列内降序权重）
    "empty_col": 6.0,        # 空列价值
    "face_up_ratio": 3.0,    # 明牌比例
}


class MovePriority(IntEnum):
    """移动优先级（数值越小越优先）"""
    COMPLETE_SEQ = 0     # 能完成完整序列
    FLIP_CARD = 1        # 能翻开暗牌
    SAME_SUIT = 2        # 同花色移动
    BUILD_SEQ = 3        # 构建序列
    TO_EMPTY = 4         # 移到空列
    DEAL = 5             # 发牌
    OTHER = 6            # 其他


# ═══════════════════════════════════════════════════
#  状态评估
# ═══════════════════════════════════════════════════

def evaluate(state: GameState) -> float:
    """
    局面评估函数 — 返回 [-100, 100] 的分数
    正值对当前玩家有利，负值不利
    """
    score = 0.0

    # 1. 已完成序列（最强信号）
    score += state.completed * _WEIGHTS["completed"]

    # 2. 同花色连续序列（已合并列内降序评分，消除双重计分）
    score += _score_same_suit_sequences(state) * _WEIGHTS["same_suit_seq"]

    # 3. 空列价值（线性）
    score += _score_empty_col(state) * _WEIGHTS["empty_col"]

    # 4. 明牌数量（线性计分）
    score += _score_face_up(state) * _WEIGHTS["face_up_ratio"]

    # 惩罚：发牌堆用完且完成数低
    if state.remaining_deals == 0 and state.completed < 4:
        score -= 10.0

    return max(-100.0, min(100.0, score))


def assess_complexity(state: GameState) -> float:
    """
    局面复杂度评估 — [0, 1]
    0 = 简单（明牌多、空列多、序列完整）
    1 = 复杂（暗牌多、无空列、序列散乱）
    """
    factors: list[float] = []

    # 暗牌比例
    total = sum(c.length for c in state.columns)
    if total > 0:
        face_down = sum(c.face_down_count for c in state.columns)
        factors.append(face_down / total)

    # 空列缺失
    factors.append(1.0 - state.empty_columns / COLUMN_COUNT)

    # 发牌堆剩余（多 = 复杂）
    factors.append(state.remaining_deals / 5.0)

    # 完成度低 = 复杂
    factors.append(1.0 - state.completed / 8.0)

    return sum(factors) / len(factors) if factors else 0.5


# ═══════════════════════════════════════════════════
#  移动评估与排序
# ═══════════════════════════════════════════════════

def move_priority(state: GameState, move: Move) -> tuple[int, float]:
    """
    评估移动优先级 — 返回 (priority_class, score)
    数值越小越优先
    """
    if move.is_deal:
        return (MovePriority.DEAL, 0.0)

    src = state.columns[move.src_col]
    dst = state.columns[move.dst_col]
    moving_cards = src.cards[move.src_start:]
    card_count = len(moving_cards)

    # 能完成完整序列？
    if _would_complete_sequence(state, move):
        return (MovePriority.COMPLETE_SEQ, -card_count)

    # 能翻开暗牌？
    remaining = src.cards[:move.src_start]
    if remaining and not remaining[-1].face_up:
        return (MovePriority.FLIP_CARD, -card_count)

    # 同花色移动
    if len(moving_cards) >= 1:
        src_suit = moving_cards[0].suit
        if not dst.is_empty:
            dst_top = dst.cards[-1]
            if dst_top.face_up and dst_top.suit == src_suit:
                return (MovePriority.SAME_SUIT, -card_count)

    # 移到空列
    if dst.is_empty:
        return (MovePriority.TO_EMPTY, -card_count)

    # 其他
    return (MovePriority.OTHER, -card_count)


def rank_moves(state: GameState, moves: Sequence[Move]) -> list[Move]:
    """按优先级排序移动列表"""
    return sorted(moves, key=lambda m: move_priority(state, m))


# ═══════════════════════════════════════════════════
#  启发式模拟（MCTS rollout 使用）
# ═══════════════════════════════════════════════════

def heuristic_rollout(
    state: GameState,
    rules,
    *,
    max_depth: int = 30,
    rng: Optional[random.Random] = None,
) -> float:
    """
    启发式引导的快速模拟 — 返回评估分数
    用于 MCTS 的 Simulation 阶段
    温度退火：前期 50% 随机探索，后期 95% 贪心利用
    """
    if rng is None:
        rng = random.Random()

    current = state
    depth = 0

    while depth < max_depth:
        outcome = rules.is_terminal(current)
        if outcome.value > 0:
            if outcome.value == 1:  # WIN
                return 100.0
            return -50.0  # DEADLOCK

        moves = rules.legal_moves(current)
        if not moves:
            if rules.can_deal(current):
                current = rules.deal(current)
                depth += 1
                continue
            return -50.0

        # 温度退火：贪心概率从 0.5 线性增长到 0.95
        progress = depth / max_depth
        greedy_prob = 0.5 + 0.45 * progress

        ranked = rank_moves(current, moves)
        if rng.random() < greedy_prob and ranked:
            chosen = ranked[0]
        else:
            chosen = rng.choice(moves)

        current = rules.apply_move(current, chosen)
        depth += 1

    return evaluate(current)


# ═══════════════════════════════════════════════════
#  内部评分函数
# ═══════════════════════════════════════════════════

def _score_same_suit_sequences(state: GameState) -> float:
    """计算同花色连续序列（从列底向上扫描，按连续段长度的三角数计分）"""
    total = 0.0
    for col in state.columns:
        if col.length < 2:
            continue
        seg_len = 1
        for i in range(col.length - 1, 0, -1):
            curr = col.cards[i]
            prev = col.cards[i - 1]
            if (curr.face_up and prev.face_up
                    and curr.suit == prev.suit
                    and prev.rank == curr.rank + 1):
                seg_len += 1
            else:
                total += seg_len * (seg_len + 1) / 2
                seg_len = 1
        total += seg_len * (seg_len + 1) / 2
    return total


def _score_empty_col(state: GameState) -> float:
    """评估空列价值（线性评分）"""
    return float(state.empty_columns)


def _score_face_up(state: GameState) -> float:
    """评估明牌数量（线性计分：每张明牌1分，信息价值与数量成正比）"""
    total = 0.0
    for col in state.columns:
        for card in col.cards:
            if card.face_up:
                total += 1.0
    return total


def _would_complete_sequence(state: GameState, move: Move) -> bool:
    """检查执行移动后是否能完成一个完整序列"""
    # 模拟移动
    src = state.columns[move.src_col]
    dst = state.columns[move.dst_col]
    moving = src.cards[move.src_start:]
    new_dst_cards = (*dst.cards, *moving)

    if len(new_dst_cards) < COMPLETE_SEQ_LEN:
        return False

    bottom_13 = new_dst_cards[-COMPLETE_SEQ_LEN:]
    if not all(c.face_up for c in bottom_13):
        return False
    suit = bottom_13[0].suit
    if not all(c.suit == suit for c in bottom_13):
        return False
    for i, card in enumerate(bottom_13):
        if int(card.rank) != Rank.K - i:
            return False
    return True
