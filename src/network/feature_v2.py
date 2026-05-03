"""
增强特征提取 v2 — 200+ 维，捕捉列间关系、红黑交替、历史信息
与 v1（58 维）完全兼容，可通过参数切换
"""

from __future__ import annotations

import math
from typing import Optional

from src.core.types import Card, CardFace, Column, GameState, Rank, Suit
from src.core.rules import RulesEngine


def extract_features_v2(state: GameState, history: Optional[list[GameState]] = None) -> list[float]:
    """
    增强特征提取 — 约 220 维

    特征组成：
    1. 每列详细特征 (15 维 × 10 列 = 150 维)
    2. 列间关系矩阵 (30 维)
    3. 全局统计 (20 维)
    4. 历史特征 (20 维)

    Returns:
        归一化到 [0, 1] 的特征向量
    """
    features = []
    cols = state.columns

    # ═══════════════════════════════════════════
    # 1. 每列详细特征 (15 维 × 10 = 150)
    # ═══════════════════════════════════════════
    for col in cols:
        cards = col.cards
        face_up = [c for c in cards if c.face == CardFace.FACE_UP]
        face_down = col.face_down_count

        if not cards:
            features.extend([0.0] * 15)
            continue

        # 1.1 顶牌 rank (归一化)
        top_rank = face_up[-1].rank / 13.0 if face_up else 0.0
        features.append(top_rank)

        # 1.2 顶牌花色 (one-hot: 4 维)
        if face_up:
            top_suit = face_up[-1].suit
            features.extend([
                1.0 if top_suit == Suit.SPADE else 0.0,
                1.0 if top_suit == Suit.HEART else 0.0,
                1.0 if top_suit == Suit.DIAMOND else 0.0,
                1.0 if top_suit == Suit.CLUB else 0.0,
            ])
        else:
            features.extend([0.0] * 4)

        # 1.3 明牌比例
        features.append(len(face_up) / max(1, len(cards)))

        # 1.4 最长同花色序列长度 / 13
        seq_len = _same_suit_seq_len(face_up)
        features.append(seq_len / 13.0)

        # 1.5 最长降序序列长度 / 13（不要求同花色）
        desc_len = _descending_seq_len(face_up)
        features.append(desc_len / 13.0)

        # 1.6 列长度 / 20
        features.append(len(cards) / 20.0)

        # 1.7 暗牌比例
        features.append(face_down / max(1, len(cards)))

        # 1.8 红黑交替模式（列内相邻牌的颜色交替次数）
        alternating = _color_alternations(face_up)
        features.append(alternating / max(1, len(face_up) - 1))

        # 1.9 花色一致性（顶牌花色占比）
        if face_up:
            top_suit = face_up[-1].suit
            same = sum(1 for c in face_up if c.suit == top_suit)
            features.append(same / len(face_up))
        else:
            features.append(0.0)

        # 1.10 可运行序列起点 rank
        runnable_start = col.runnable_start()
        features.append(runnable_start / 13.0 if runnable_start else 0.0)

        # 1.11 空列标志
        features.append(1.0 if col.is_empty else 0.0)

        # 1.12 底牌 rank（如果可见）
        bottom = cards[0] if cards else None
        features.append(bottom.rank / 13.0 if bottom and bottom.face == CardFace.FACE_UP else 0.0)

        # 1.13 K 存在标志（是否有 K 在列顶）
        has_k = 1.0 if face_up and face_up[-1].rank == Rank.K else 0.0
        features.append(has_k)

    # ═══════════════════════════════════════════
    # 2. 列间关系特征 (30 维)
    # ═══════════════════════════════════════════
    top_cards = []
    for col in cols:
        face_up = [c for c in col.cards if c.face == CardFace.FACE_UP]
        top_cards.append(face_up[-1] if face_up else None)

    # 2.1 可移动对数（源列顶牌 rank - 1 == 目标列顶牌 rank）
    movable_pairs = 0
    for i in range(10):
        for j in range(10):
            if i != j and top_cards[i] and top_cards[j]:
                if top_cards[i].rank + 1 == top_cards[j].rank:
                    movable_pairs += 1
    features.append(movable_pairs / 90.0)  # 最多 90 对

    # 2.2 同花色可移动对数
    same_suit_pairs = 0
    for i in range(10):
        for j in range(10):
            if i != j and top_cards[i] and top_cards[j]:
                if (top_cards[i].suit == top_cards[j].suit
                        and top_cards[i].rank + 1 == top_cards[j].rank):
                    same_suit_pairs += 1
    features.append(same_suit_pairs / 90.0)

    # 2.3 花色分布（每种花色的顶牌数量）
    for suit in Suit:
        count = sum(1 for c in top_cards if c and c.suit == suit)
        features.append(count / 10.0)

    # 2.4 红色/黑色顶牌比例
    red_tops = sum(1 for c in top_cards if c and c.suit.is_red)
    black_tops = sum(1 for c in top_cards if c and not c.suit.is_red)
    features.append(red_tops / 10.0)
    features.append(black_tops / 10.0)

    # 2.5 Rank 分布（顶牌 rank 的标准差）
    visible_ranks = [c.rank for c in top_cards if c]
    if len(visible_ranks) > 1:
        import statistics
        rank_std = statistics.stdev(visible_ranks) / 13.0
    else:
        rank_std = 0.0
    features.append(rank_std)

    # 2.6 最大 rank 差（最高顶牌 rank - 最低顶牌 rank）
    if visible_ranks:
        rank_range = (max(visible_ranks) - min(visible_ranks)) / 13.0
    else:
        rank_range = 0.0
    features.append(rank_range)

    # 2.7 连续降序对（相邻列顶牌是否构成降序）
    consecutive_desc = 0
    for i in range(9):
        if top_cards[i] and top_cards[i + 1]:
            if top_cards[i].rank == top_cards[i + 1].rank + 1:
                consecutive_desc += 1
    features.append(consecutive_desc / 9.0)

    # 2.8 可完成序列候选数（列顶有 K 且列内有完整的 K→A 同花色序列潜力）
    k_columns = sum(1 for c in top_cards if c and c.rank == Rank.K)
    features.append(k_columns / 10.0)

    # 2.9-2.12 列高度分布（短列/中列/长列比例）
    short = sum(1 for col in cols if 0 < col.length <= 3)
    medium = sum(1 for col in cols if 3 < col.length <= 6)
    long_ = sum(1 for col in cols if col.length > 6)
    features.extend([short / 10.0, medium / 10.0, long_ / 10.0])

    # 2.13-2.16 顶牌 rank 分桶（A-4, 5-8, 9-J, K-Q）
    low_ranks = sum(1 for c in top_cards if c and c.rank <= 4)
    mid_ranks = sum(1 for c in top_cards if c and 5 <= c.rank <= 8)
    high_ranks = sum(1 for c in top_cards if c and 9 <= c.rank <= 11)
    ace_kings = sum(1 for c in top_cards if c and (c.rank == 1 or c.rank == 13))
    features.extend([low_ranks / 10.0, mid_ranks / 10.0, high_ranks / 10.0, ace_kings / 10.0])

    # 2.17-2.22 补充到 30 维
    # 发牌堆剩余批次的花色分布估计
    features.append(state.remaining_deals / 5.0)
    features.append(1.0 if state.remaining_deals == 0 else 0.0)
    features.append(1.0 if state.remaining_deals >= 3 else 0.0)
    # 已完成序列的花色分布
    features.append(state.completed / 8.0)
    features.append(1.0 if state.completed >= 4 else 0.0)
    features.append(1.0 if state.completed >= 7 else 0.0)

    # ═══════════════════════════════════════════
    # 3. 全局统计 (20 维)
    # ═══════════════════════════════════════════
    total_face_down = sum(c.face_down_count for c in cols)
    total_face_up = sum(len([c for c in col.cards if c.face == CardFace.FACE_UP]) for col in cols)
    empty_cols = state.empty_columns
    total_cards = sum(col.length for col in cols)

    features.append(state.remaining_deals / 5.0)
    features.append(state.completed / 8.0)
    features.append(total_face_down / 50.0)
    features.append(total_face_up / 54.0)
    features.append(empty_cols / 10.0)
    features.append(state.move_count / 500.0)
    features.append(state.difficulty / 4.0)
    features.append(1.0 if state.difficulty == 1 else 0.0)
    features.append(total_cards / 104.0)

    # 同花色序列总数
    total_same_suit = sum(_same_suit_seq_len([c for c in col.cards if c.face == CardFace.FACE_UP]) for col in cols)
    features.append(total_same_suit / 80.0)

    # 降序序列总数
    total_desc = sum(_descending_seq_len([c for c in col.cards if c.face == CardFace.FACE_UP]) for col in cols)
    features.append(total_desc / 80.0)

    # 最大列长度 / 20
    max_col_len = max((col.length for col in cols), default=0)
    features.append(max_col_len / 20.0)

    # 最小列长度 / 20
    non_empty = [col.length for col in cols if not col.is_empty]
    min_col_len = min(non_empty) if non_empty else 0
    features.append(min_col_len / 20.0)

    # 列长度标准差
    if len(non_empty) > 1:
        import statistics
        col_len_std = statistics.stdev(non_empty) / 10.0
    else:
        col_len_std = 0.0
    features.append(col_len_std)

    # 明牌中 A 的数量
    aces_up = sum(
        1 for col in cols
        for c in col.cards
        if c.face == CardFace.FACE_UP and c.rank == Rank.A
    )
    features.append(aces_up / 8.0)

    # 明牌中 K 的数量
    kings_up = sum(
        1 for col in cols
        for c in col.cards
        if c.face == CardFace.FACE_UP and c.rank == Rank.K
    )
    features.append(kings_up / 8.0)

    # 发牌堆可行性（无空列才能发牌）
    can_deal = 1.0 if empty_cols == 0 and state.remaining_deals > 0 else 0.0
    features.append(can_deal)

    # 近似复杂度（暗牌比例 × 列数 / 空列数）
    complexity = (total_face_down / max(1, total_cards)) * (10 / max(1, 10 - empty_cols))
    features.append(min(1.0, complexity))

    # 步数效率（已完成 / 步数）
    step_eff = state.completed / max(1, state.move_count)
    features.append(step_eff)

    # ═══════════════════════════════════════════
    # 4. 历史特征 (20 维)
    # ═══════════════════════════════════════════
    if history and len(history) >= 2:
        recent = history[-min(10, len(history)):]
        # 4.1 近期完成数变化
        completed_changes = [
            recent[i].completed - recent[i-1].completed
            for i in range(1, len(recent))
        ]
        features.append(sum(completed_changes) / max(1, len(completed_changes)))
        features.append(max(completed_changes) if completed_changes else 0.0)

        # 4.2 近期空列变化
        empty_changes = [
            recent[i].empty_columns - recent[i-1].empty_columns
            for i in range(1, len(recent))
        ]
        features.append(sum(empty_changes) / max(1, len(empty_changes)))

        # 4.3 近期暗牌翻牌数
        fd_changes = [
            sum(c.face_down_count for c in recent[i-1].columns)
            - sum(c.face_down_count for c in recent[i].columns)
            for i in range(1, len(recent))
        ]
        features.append(sum(fd_changes) / max(1, len(fd_changes)))

        # 4.4 步数增速
        features.append(len(recent) / 500.0)

        # 4.5-4.10 近期评估分数趋势
        from src.strategy.heuristics import evaluate
        recent_scores = [evaluate(s) for s in recent[-5:]]
        if len(recent_scores) >= 2:
            score_trend = (recent_scores[-1] - recent_scores[0]) / 200.0
            features.append(max(-1.0, min(1.0, score_trend)))
            features.append(max(recent_scores) / 100.0)
            features.append(min(recent_scores) / 100.0)
        else:
            features.extend([0.0, 0.0, 0.0])

        # 4.7-4.12 补充到 20 维
        features.extend([0.0] * (20 - len(features) + len(features[:-(20)] if len(features) > 170 else features)))
    else:
        features.extend([0.0] * 20)

    # 确保总维度为 220
    while len(features) < 220:
        features.append(0.0)
    features = features[:220]

    return features


def _same_suit_seq_len(face_up: list[Card]) -> int:
    """从列顶开始的同花色降序序列长度"""
    if len(face_up) < 2:
        return len(face_up)
    seq_len = 1
    for i in range(len(face_up) - 1, 0, -1):
        curr = face_up[i]
        prev = face_up[i - 1]
        if curr.suit == prev.suit and prev.rank == curr.rank + 1:
            seq_len += 1
        else:
            break
    return seq_len


def _descending_seq_len(face_up: list[Card]) -> int:
    """从列顶开始的降序序列长度（不要求同花色）"""
    if len(face_up) < 2:
        return len(face_up)
    seq_len = 1
    for i in range(len(face_up) - 1, 0, -1):
        curr = face_up[i]
        prev = face_up[i - 1]
        if prev.rank == curr.rank + 1:
            seq_len += 1
        else:
            break
    return seq_len


def _color_alternations(face_up: list[Card]) -> int:
    """计算列内相邻牌的颜色交替次数"""
    if len(face_up) < 2:
        return 0
    count = 0
    for i in range(len(face_up) - 1, 0, -1):
        if face_up[i].suit.is_red != face_up[i-1].suit.is_red:
            count += 1
    return count
