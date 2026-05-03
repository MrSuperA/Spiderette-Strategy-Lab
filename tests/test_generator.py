"""Tests for src.envs.generator — generate_game, generate_batch."""

import pytest
from src.envs.generator import generate_game, generate_batch


class TestGenerateGame:
    def test_produces_10_columns(self):
        state = generate_game(seed=42)
        assert len(state.columns) == 10

    def test_total_cards_is_104(self):
        """Initial deal (54) + stock (5*10) = 104."""
        state = generate_game(seed=42)
        assert state.total_cards == 104

    def test_total_cards_104_all_difficulties(self):
        for diff in (1, 2, 4):
            state = generate_game(seed=1, difficulty=diff)
            assert state.total_cards == 104, f"Failed for difficulty={diff}"

    def test_different_seeds_different_states(self):
        s1 = generate_game(seed=1)
        s2 = generate_game(seed=2)
        # At least one column should differ
        differ = any(
            s1.columns[i].cards != s2.columns[i].cards for i in range(10)
        )
        assert differ

    def test_same_seed_reproducible(self):
        s1 = generate_game(seed=999)
        s2 = generate_game(seed=999)
        for i in range(10):
            assert s1.columns[i].cards == s2.columns[i].cards
        assert s1.seed == s2.seed

    def test_initial_layout_columns(self):
        """First 4 columns have 6 cards, last 6 have 5 cards."""
        state = generate_game(seed=1)
        for i in range(4):
            assert state.columns[i].length == 6
        for i in range(4, 10):
            assert state.columns[i].length == 5

    def test_top_card_is_face_up(self):
        state = generate_game(seed=1)
        for col in state.columns:
            assert col.top_card is not None
            assert col.top_card.face_up is True

    def test_stock_has_5_tokens(self):
        state = generate_game(seed=1)
        assert len(state.stock) == 5


class TestGenerateBatch:
    def test_correct_count(self):
        batch = generate_batch(count=5, seed_start=10)
        assert len(batch) == 5

    def test_seeds_are_sequential(self):
        batch = generate_batch(count=3, seed_start=10)
        assert batch[0].seed == 10
        assert batch[1].seed == 11
        assert batch[2].seed == 12

    def test_empty_batch(self):
        batch = generate_batch(count=0)
        assert len(batch) == 0
