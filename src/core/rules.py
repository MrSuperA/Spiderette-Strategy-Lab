"""
规则引擎 — 纯函数集合，无状态无副作用
职责：合法移动检测、状态转换、胜负判定
设计原则：所有方法返回新 GameState（不可变），不修改入参
"""

from __future__ import annotations

from typing import Optional, Sequence

from src.core.types import (
    Card,
    CardFace,
    Column,
    GameState,
    Move,
    Outcome,
    Rank,
    Suit,
)

# ── 常量 ──

TOTAL_CARDS = 104
COLUMN_COUNT = 10
COMPLETE_SEQ_LEN = 13
INITIAL_DEAL_CARDS = 54
DEAL_BATCH = 10
MAX_DEALS = 5


class RulesEngine:
    """
    蜘蛛纸牌规则引擎（满足 Rules 协议）
    所有公开方法均为纯函数，不修改输入状态
    """

    # ── 公开接口 ──

    def legal_moves(self, state: GameState) -> Sequence[Move]:
        """返回所有合法移牌操作（不含发牌）"""
        moves: list[Move] = []
        for src_idx in range(COLUMN_COUNT):
            src_col = state.columns[src_idx]
            if src_col.is_empty:
                continue
            seq_start = src_col.runnable_start()
            # 从序列起始开始，只取序列整体（禁止拆分可运行序列）
            start = seq_start
            card_count = src_col.length - start
            # 移动的牌必须全部面朝上
            if not all(c.face_up for c in src_col.cards[start:]):
                continue
            for dst_idx in range(COLUMN_COUNT):
                if dst_idx == src_idx:
                    continue
                if self._is_valid_placement(state, start, src_idx, dst_idx):
                    moves.append(Move(
                        src_col=src_idx,
                        src_start=start,
                        dst_col=dst_idx,
                        card_count=card_count,
                    ))
        # 多牌优先排序
        moves.sort(key=lambda m: -m.card_count)
        return moves

    def apply_move(self, state: GameState, move: Move) -> GameState:
        """执行移牌，返回新状态（不可变）"""
        if move.is_deal:
            return self.deal(state)

        columns = list(state.columns)
        src = columns[move.src_col]
        dst = columns[move.dst_col]

        # 取出要移动的牌
        moving = src.cards[move.src_start:]
        remaining = src.cards[:move.src_start]

        # 翻开源列新底牌
        if remaining and not remaining[-1].face_up:
            remaining = (*remaining[:-1], Card(
                suit=remaining[-1].suit,
                rank=remaining[-1].rank,
                face=CardFace.FACE_UP,
            ))

        columns[move.src_col] = Column(cards=tuple(remaining))
        columns[move.dst_col] = Column(cards=(*dst.cards, *moving))

        new_state = GameState(
            columns=tuple(columns),
            stock=state.stock,
            completed=state.completed,
            difficulty=state.difficulty,
            move_count=state.move_count + 1,
            seed=state.seed,
        )

        # 检查是否有完整的 K→A 序列可移除
        return self._check_and_remove_sequence(new_state, move.dst_col)

    def deal(self, state: GameState) -> GameState:
        """发牌：从 stock 取一批牌分配到 10 列"""
        if not self.can_deal(state):
            return state

        stock = state.stock
        new_card_specs = self._generate_deal_cards(stock[0], state.difficulty)
        columns = list(state.columns)

        for i, card in enumerate(new_card_specs):
            columns[i] = Column(cards=(*columns[i].cards, card))

        return GameState(
            columns=tuple(columns),
            stock=stock[1:],
            completed=state.completed,
            difficulty=state.difficulty,
            move_count=state.move_count + 1,
            seed=state.seed,
        )

    def can_deal(self, state: GameState) -> bool:
        """是否可以发牌：有剩余 stock 且无空列"""
        if state.remaining_deals <= 0:
            return False
        return state.empty_columns == 0

    def is_win(self, state: GameState) -> bool:
        return state.completed >= 8

    def is_deadlock(self, state: GameState) -> bool:
        """死局：无法发牌 且 无合法移动"""
        if not self.is_win(state) and self.can_deal(state):
            return False
        return len(self.legal_moves(state)) == 0 and not self.is_win(state)

    def is_terminal(self, state: GameState) -> Outcome:
        if self.is_win(state):
            return Outcome.WIN
        if len(self.legal_moves(state)) == 0 and not self.can_deal(state):
            return Outcome.DEADLOCK
        return Outcome.PLAYING

    # ── 内部方法 ──

    def _is_valid_placement(
        self, state: GameState, src_start: int, src_idx: int, dst_idx: int
    ) -> bool:
        """检查从 src_col[src_start:] 能否移到 dst_col"""
        src_col = state.columns[src_idx]
        dst_col = state.columns[dst_idx]
        moving_card = src_col.cards[src_start]

        if not moving_card.face_up:
            return False

        if dst_col.is_empty:
            # 空列允许放任何序列
            return True

        dst_top = dst_col.cards[-1]
        if not dst_top.face_up:
            return False

        # 目标顶牌必须比移动首牌大 1
        return int(dst_top.rank) == int(moving_card.rank) + 1

    def _check_and_remove_sequence(self, state: GameState, col_idx: int) -> GameState:
        """检查指定列底部是否有完整 K→A 同花色序列，有则移除"""
        col = state.columns[col_idx]
        if col.length < COMPLETE_SEQ_LEN:
            return state

        bottom_13 = col.cards[-COMPLETE_SEQ_LEN:]

        # 全部面朝上
        if not all(c.face_up for c in bottom_13):
            return state

        # 同花色
        suit = bottom_13[0].suit
        if not all(c.suit == suit for c in bottom_13):
            return state

        # K→A 递减
        for i, card in enumerate(bottom_13):
            expected = Rank.K - i
            if int(card.rank) != expected:
                return state

        # 移除序列
        remaining = col.cards[:-COMPLETE_SEQ_LEN]
        columns = list(state.columns)
        columns[col_idx] = Column(cards=remaining)

        return GameState(
            columns=tuple(columns),
            stock=state.stock,
            completed=state.completed + 1,
            difficulty=state.difficulty,
            move_count=state.move_count,
            seed=state.seed,
        )

    def _generate_deal_cards(self, stock_token: Card, difficulty: int) -> list[Card]:
        """根据 stock token 和难度生成发牌序列（10张）"""
        # stock token 的 suit 决定这批发牌的花色
        # 1花色：全黑桃；2花色：随机红/黑；4花色：随机四种
        if difficulty == 1:
            suits = [Suit.SPADE] * 10
        elif difficulty == 2:
            import random
            rng = random.Random(stock_token.suit * 100 + stock_token.rank)
            suits = [rng.choice([Suit.SPADE, Suit.HEART]) for _ in range(10)]
        else:
            import random
            rng = random.Random(stock_token.suit * 100 + stock_token.rank)
            suits = [rng.choice(list(Suit)) for _ in range(10)]

        # 点数随机分配（使用 stock token 作为种子确保可复现）
        import random
        rng = random.Random(stock_token.rank * 10 + stock_token.suit)
        ranks = rng.sample(list(Rank), 10) if difficulty <= 2 else rng.sample(list(Rank), 10)

        return [Card(suit=s, rank=r, face=CardFace.FACE_UP) for s, r in zip(suits, ranks)]
