"""Tests for src.core.types — data models, enums, protocols."""

import pytest
from src.core.types import (
    Card,
    CardFace,
    Column,
    Difficulty,
    GameState,
    Move,
    Outcome,
    Rank,
    Suit,
)


# ── Suit enum ──

class TestSuit:
    def test_values(self):
        assert Suit.SPADE.value == 0
        assert Suit.HEART.value == 1
        assert Suit.DIAMOND.value == 2
        assert Suit.CLUB.value == 3

    def test_symbols(self):
        assert Suit.SPADE.symbol == "♠"
        assert Suit.HEART.symbol == "♥"
        assert Suit.DIAMOND.symbol == "♦"
        assert Suit.CLUB.symbol == "♣"

    def test_is_red(self):
        assert not Suit.SPADE.is_red
        assert Suit.HEART.is_red
        assert Suit.DIAMOND.is_red
        assert not Suit.CLUB.is_red

    def test_str(self):
        assert str(Suit.SPADE) == "♠"
        assert str(Suit.HEART) == "♥"


# ── Rank enum ──

class TestRank:
    def test_values(self):
        assert Rank.A.value == 1
        assert Rank._10.value == 10
        assert Rank.K.value == 13

    def test_str_repr(self):
        assert str(Rank.A) == "A"
        assert str(Rank._2) == "2"
        assert str(Rank._10) == "10"
        assert str(Rank.J) == "J"
        assert str(Rank.Q) == "Q"
        assert str(Rank.K) == "K"


# ── Card ──

class TestCard:
    def test_creation(self):
        c = Card(Suit.SPADE, Rank.A)
        assert c.suit == Suit.SPADE
        assert c.rank == Rank.A
        assert c.face == CardFace.FACE_UP  # default

    def test_face_up_property(self):
        up = Card(Suit.HEART, Rank._5, CardFace.FACE_UP)
        down = Card(Suit.HEART, Rank._5, CardFace.FACE_DOWN)
        assert up.face_up is True
        assert down.face_up is False

    def test_color(self):
        red = Card(Suit.HEART, Rank.A)
        black = Card(Suit.SPADE, Rank.A)
        assert red.color == "red"
        assert black.color == "black"

    def test_str_visible(self):
        c = Card(Suit.SPADE, Rank.K, CardFace.FACE_UP)
        assert "♠" in str(c) and "K" in str(c)

    def test_str_hidden(self):
        c = Card(Suit.SPADE, Rank.K, CardFace.FACE_DOWN)
        assert str(c) == "??"

    def test_to_dict(self):
        c = Card(Suit.HEART, Rank.Q, CardFace.FACE_UP)
        d = c.to_dict()
        assert d["suit"] == "♥"
        assert d["rank"] == "Q"
        assert d["red"] is True
        assert d["face_up"] is True


# ── Column ──

class TestColumn:
    def test_empty_column(self):
        col = Column()
        assert col.length == 0
        assert col.is_empty is True
        assert col.top_card is None
        assert col.face_up_count == 0
        assert col.runnable_start() == 0

    def test_single_card(self):
        c = Card(Suit.SPADE, Rank.K, CardFace.FACE_UP)
        col = Column(cards=(c,))
        assert col.length == 1
        assert col.is_empty is False
        assert col.top_card == c
        assert col.face_up_count == 1

    def test_mixed_face(self):
        c1 = Card(Suit.SPADE, Rank.K, CardFace.FACE_DOWN)
        c2 = Card(Suit.HEART, Rank.Q, CardFace.FACE_UP)
        col = Column(cards=(c1, c2))
        assert col.face_up_count == 1
        assert col.face_down_count == 1

    def test_runnable_start_same_suit_sequence(self):
        """A same-suit descending sequence should be detected."""
        cards = (
            Card(Suit.SPADE, Rank._5, CardFace.FACE_DOWN),
            Card(Suit.SPADE, Rank.K, CardFace.FACE_UP),
            Card(Suit.SPADE, Rank.Q, CardFace.FACE_UP),
            Card(Suit.SPADE, Rank.J, CardFace.FACE_UP),
        )
        col = Column(cards=cards)
        start = col.runnable_start()
        assert start == 1  # K-Q-J is the runnable sequence


# ── GameState ──

class TestGameState:
    def test_creation(self, simple_state):
        assert len(simple_state.columns) == 10
        assert simple_state.completed == 0
        assert simple_state.difficulty == 2

    def test_total_cards(self, simple_state):
        """Simple state: 10 cards in columns + 5*10 stock + 0*13 completed = 60."""
        assert simple_state.total_cards == 10 + 50 + 0

    def test_empty_columns(self, simple_state):
        """All columns have one card, so zero empty."""
        assert simple_state.empty_columns == 0

    def test_remaining_deals(self, simple_state):
        assert simple_state.remaining_deals == 5

    def test_must_have_10_columns(self):
        with pytest.raises(ValueError, match="Expected 10 columns"):
            GameState(
                columns=tuple(Column() for _ in range(5)),
                stock=(),
            )

    def test_to_dict(self, simple_state):
        d = simple_state.to_dict()
        assert "columns" in d
        assert len(d["columns"]) == 10
        assert d["stock_remaining"] == 5
        assert d["completed"] == 0


# ── Move ──

class TestMove:
    def test_creation(self):
        m = Move(src_col=0, src_start=3, dst_col=5, card_count=2)
        assert m.src_col == 0
        assert m.src_start == 3
        assert m.dst_col == 5
        assert m.card_count == 2

    def test_is_deal(self):
        deal_move = Move(src_col=0, src_start=0, dst_col=-1)
        assert deal_move.is_deal is True

    def test_is_not_deal(self):
        move = Move(src_col=0, src_start=0, dst_col=1)
        assert move.is_deal is False

    def test_to_dict_deal(self):
        d = Move(src_col=0, src_start=0, dst_col=-1).to_dict()
        assert d == {"action": "deal"}

    def test_to_dict_move(self):
        d = Move(src_col=2, src_start=4, dst_col=7, card_count=3).to_dict()
        assert d["action"] == "move"
        assert d["src"] == 2
        assert d["dst"] == 7


# ── Frozen immutability ──

class TestFrozen:
    def test_card_immutable(self):
        c = Card(Suit.SPADE, Rank.A)
        with pytest.raises(AttributeError):
            c.rank = Rank.K  # type: ignore[misc]

    def test_column_immutable(self):
        col = Column(cards=())
        with pytest.raises(AttributeError):
            col.cards = (Card(Suit.SPADE, Rank.A),)  # type: ignore[misc]

    def test_gamestate_immutable(self, simple_state):
        with pytest.raises(AttributeError):
            simple_state.completed = 8  # type: ignore[misc]

    def test_move_immutable(self):
        m = Move(src_col=0, src_start=0, dst_col=1)
        with pytest.raises(AttributeError):
            m.src_col = 5  # type: ignore[misc]
