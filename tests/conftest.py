"""
Shared fixtures for Spiderette Strategy Lab tests.
Provides reusable GameState, RulesEngine, and factory fixtures.
"""

import pytest

from src.core.types import (
    Card,
    CardFace,
    Column,
    GameState,
    Move,
    Rank,
    Suit,
)
from src.core.rules import RulesEngine
from src.envs.generator import generate_game


@pytest.fixture
def rules_engine() -> RulesEngine:
    """A fresh RulesEngine instance."""
    return RulesEngine()


@pytest.fixture
def simple_state() -> GameState:
    """
    A minimal valid GameState with 10 columns.
    Each column has one face-up card; stock has 5 tokens; no sequences completed.
    Suitable for basic property checks and move generation.
    """
    cards = [
        Card(Suit.SPADE, Rank.K, CardFace.FACE_UP),
        Card(Suit.HEART, Rank.Q, CardFace.FACE_UP),
        Card(Suit.DIAMOND, Rank.J, CardFace.FACE_UP),
        Card(Suit.CLUB, Rank._10, CardFace.FACE_UP),
        Card(Suit.SPADE, Rank._9, CardFace.FACE_UP),
        Card(Suit.HEART, Rank._8, CardFace.FACE_UP),
        Card(Suit.DIAMOND, Rank._7, CardFace.FACE_UP),
        Card(Suit.CLUB, Rank._6, CardFace.FACE_UP),
        Card(Suit.SPADE, Rank._5, CardFace.FACE_UP),
        Card(Suit.HEART, Rank._4, CardFace.FACE_UP),
    ]
    columns = tuple(Column(cards=(c,)) for c in cards)
    # Stock: 5 batches of 10 cards each (50 total)
    stock = tuple(
        tuple(
            Card(Suit(j % 4), Rank((j % 13) + 1), CardFace.FACE_UP)
            for j in range(i * 10, (i + 1) * 10)
        )
        for i in range(5)
    )
    return GameState(
        columns=columns,
        stock=stock,
        completed=0,
        difficulty=2,
        move_count=0,
        seed=42,
    )


@pytest.fixture
def generated_state() -> GameState:
    """A randomly-generated initial game state (seed=1)."""
    return generate_game(seed=1, difficulty=2)


@pytest.fixture
def make_state():
    """
    Factory fixture: call make_state(columns, stock, completed, ...) to build
    a GameState with custom parameters while keeping sensible defaults.
    """

    def _make(
        columns=None,
        stock=None,
        completed: int = 0,
        difficulty: int = 2,
        move_count: int = 0,
        seed: int = 0,
    ) -> GameState:
        if columns is None:
            columns = tuple(
                Column(cards=(
                    Card(Suit(i % 4), Rank(13 - i), CardFace.FACE_UP),
                ))
                for i in range(10)
            )
        if stock is None:
            stock = tuple(
                tuple(
                    Card(Suit(j % 4), Rank((j % 13) + 1), CardFace.FACE_UP)
                    for j in range(i * 10, (i + 1) * 10)
                )
                for i in range(5)
            )
        return GameState(
            columns=columns,
            stock=stock,
            completed=completed,
            difficulty=difficulty,
            move_count=move_count,
            seed=seed,
        )

    return _make
