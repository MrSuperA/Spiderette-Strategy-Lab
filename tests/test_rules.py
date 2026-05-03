"""Tests for src.core.rules — RulesEngine: moves, apply, deal, win/deadlock detection."""

import pytest
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
from src.core.rules import RulesEngine
from src.envs.generator import generate_game


# ── legal_moves ──

class TestLegalMoves:
    def test_initial_state_has_moves(self, rules_engine, generated_state):
        """A freshly generated game should have at least some legal moves."""
        moves = rules_engine.legal_moves(generated_state)
        assert isinstance(moves, list)
        assert len(moves) > 0

    def test_moves_are_sorted_by_card_count_desc(self, rules_engine, generated_state):
        """Moves should be sorted with larger moves first."""
        moves = rules_engine.legal_moves(generated_state)
        if len(moves) > 1:
            for i in range(len(moves) - 1):
                assert moves[i].card_count >= moves[i + 1].card_count

    def test_moves_to_empty_columns(self, rules_engine):
        """With one non-empty column, cards can move to any empty column."""
        c = Card(Suit.SPADE, Rank.K, CardFace.FACE_UP)
        columns = [Column()] * 9 + [Column(cards=(c,))]
        state = GameState(
            columns=tuple(columns),
            stock=(),
            completed=0,
        )
        moves = rules_engine.legal_moves(state)
        # 移牌到空列是合法操作
        assert len(moves) == 9
        assert all(m.dst_col != 9 for m in moves)


# ── apply_move ──

class TestApplyMove:
    def test_returns_new_state(self, rules_engine, simple_state):
        """apply_move must return a NEW state, not mutate the original."""
        moves = rules_engine.legal_moves(simple_state)
        if moves:
            new_state = rules_engine.apply_move(simple_state, moves[0])
            assert new_state is not simple_state
            assert new_state.move_count == simple_state.move_count + 1

    def test_move_count_increments(self, rules_engine, generated_state):
        moves = rules_engine.legal_moves(generated_state)
        if moves:
            new_state = rules_engine.apply_move(generated_state, moves[0])
            assert new_state.move_count == generated_state.move_count + 1

    def test_face_down_card_flipped_after_move(self, rules_engine, make_state):
        """When a face-up card is moved away and reveals a face-down card, it should flip."""
        # Column 0: [face-down K, face-up Q]  — move Q to column 1 which is empty
        src = Column(cards=(
            Card(Suit.SPADE, Rank.K, CardFace.FACE_DOWN),
            Card(Suit.SPADE, Rank.Q, CardFace.FACE_UP),
        ))
        dst = Column()
        other = Column(cards=(Card(Suit.HEART, Rank._3, CardFace.FACE_UP),))
        columns = [src, dst] + [other] * 8
        state = make_state(columns=tuple(columns), stock=())
        move = Move(src_col=0, src_start=1, dst_col=1, card_count=1)
        new_state = rules_engine.apply_move(state, move)
        # The K in column 0 should now be face-up
        assert new_state.columns[0].cards[0].face_up is True

    def test_deal_move(self, rules_engine, simple_state):
        """A deal Move (dst_col=-1) should call deal internally."""
        move = Move(src_col=0, src_start=0, dst_col=-1)
        new_state = rules_engine.apply_move(simple_state, move)
        assert new_state.remaining_deals == simple_state.remaining_deals - 1


# ── deal ──

class TestDeal:
    def test_deal_adds_cards(self, rules_engine, simple_state):
        new_state = rules_engine.deal(simple_state)
        # Each column should have one more card
        for i in range(10):
            assert new_state.columns[i].length == simple_state.columns[i].length + 1

    def test_deal_reduces_stock(self, rules_engine, simple_state):
        new_state = rules_engine.deal(simple_state)
        assert new_state.remaining_deals == simple_state.remaining_deals - 1

    def test_deal_returns_same_when_cannot_deal(self, rules_engine):
        """Dealing when stock is empty returns the same state."""
        state = GameState(
            columns=tuple(Column() for _ in range(10)),
            stock=(),
            completed=0,
        )
        # can_deal is False because empty columns exist
        # but even if we force it, deal should return state unchanged
        result = rules_engine.deal(state)
        assert result.remaining_deals == 0


# ── can_deal ──

class TestCanDeal:
    def test_can_deal_with_stock_and_no_empty_columns(self, rules_engine, simple_state):
        assert rules_engine.can_deal(simple_state) is True

    def test_cannot_deal_with_empty_columns(self, rules_engine, make_state):
        columns = [Column()] + [Column(cards=(Card(Suit.SPADE, Rank.A, CardFace.FACE_UP),))] * 9
        state = make_state(columns=tuple(columns), stock=())
        assert rules_engine.can_deal(state) is False

    def test_cannot_deal_without_stock(self, rules_engine, make_state):
        columns = [Column(cards=(Card(Suit.SPADE, Rank.A, CardFace.FACE_UP),))] * 10
        state = make_state(columns=tuple(columns), stock=())
        assert rules_engine.can_deal(state) is False


# ── is_win ──

class TestIsWin:
    def test_not_win_initially(self, rules_engine, simple_state):
        assert rules_engine.is_win(simple_state) is False

    def test_win_when_8_completed(self, rules_engine, make_state):
        state = make_state(completed=8)
        assert rules_engine.is_win(state) is True

    def test_not_win_with_7_completed(self, rules_engine, make_state):
        state = make_state(completed=7)
        assert rules_engine.is_win(state) is False


# ── is_terminal / Outcome ──

class TestIsTerminal:
    def test_initial_state_is_playing(self, rules_engine, generated_state):
        assert rules_engine.is_terminal(generated_state) == Outcome.PLAYING

    def test_win_state(self, rules_engine, make_state):
        state = make_state(completed=8)
        assert rules_engine.is_terminal(state) == Outcome.WIN

    def test_deadlock_state(self, rules_engine, make_state):
        """No legal moves, no stock, not win => DEADLOCK."""
        columns = [Column(cards=(Card(Suit.SPADE, Rank.A, CardFace.FACE_UP),))] * 10
        state = make_state(columns=tuple(columns), stock=())
        # Only one card per column, no moves possible (A can't go on A same rank)
        assert rules_engine.is_terminal(state) == Outcome.DEADLOCK


# ── is_deadlock ──

class TestIsDeadlock:
    def test_not_deadlock_initially(self, rules_engine, generated_state):
        assert rules_engine.is_deadlock(generated_state) is False

    def test_deadlock_no_moves_no_stock(self, rules_engine, make_state):
        columns = [Column(cards=(Card(Suit.SPADE, Rank.A, CardFace.FACE_UP),))] * 10
        state = make_state(columns=tuple(columns), stock=())
        assert rules_engine.is_deadlock(state) is True


# ── Sequence detection and removal ──

class TestSequenceRemoval:
    def test_complete_k_to_a_same_suit_removed(self, rules_engine, make_state):
        """A move that creates a K→A same-suit sequence should remove it."""
        # col 0: A♠ (face-up, single)
        # col 1: K→2♠ (12 cards descending, same suit)
        # Move A♠ onto col 1 → K→A♠ (13 cards) → removed
        col_source = Column(cards=(Card(Suit.SPADE, Rank.A, CardFace.FACE_UP),))

        descending = tuple(
            Card(Suit.SPADE, Rank(13 - i), CardFace.FACE_UP) for i in range(12)
        )  # K,Q,J,...,3,2 (rank 13 down to 2)
        col_target = Column(cards=descending)

        columns = [col_source, col_target] + [
            Column(cards=(Card(Suit.HEART, Rank._3, CardFace.FACE_UP),))
        ] * 8
        state = make_state(columns=tuple(columns), stock=())

        # Move A♠ (src_start=0, runnable_start=0) to col 1 (dst_top=2♠, 2==1+1 ✓)
        move = Move(src_col=0, src_start=0, dst_col=1, card_count=1)
        new_state = rules_engine.apply_move(state, move)
        assert new_state.completed == 1
        assert new_state.columns[1].length == 0  # sequence removed
