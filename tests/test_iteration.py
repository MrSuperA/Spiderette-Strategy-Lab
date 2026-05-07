"""
迭代引擎测试 — 策略清单、迭代记录、迭代引擎
"""

import json
import pytest
from pathlib import Path
from src.iteration.engine import (
    StrategyManifest,
    IterationRecord,
    ImprovementAction,
    IterationEngine,
)


class TestStrategyManifest:
    """策略清单"""

    def test_create(self):
        m = StrategyManifest(name="mcts", display_name="MCTS", params={"iterations": 500})
        assert m.name == "mcts"
        assert m.params == {"iterations": 500}

    def test_to_dict_from_dict(self):
        m = StrategyManifest(name="mcts", display_name="MCTS", params={"iterations": 500})
        d = m.to_dict()
        m2 = StrategyManifest.from_dict(d)
        assert m2.name == m.name
        assert m2.params == m.params

    def test_save_load(self, tmp_path):
        m = StrategyManifest(name="mcts", display_name="MCTS", params={"iterations": 500})
        path = m.save(tmp_path / "test_manifest.json")
        assert path.exists()
        m2 = StrategyManifest.load(path)
        assert m2.name == "mcts"
        assert m2.params == {"iterations": 500}

    def test_create_strategy(self):
        m = StrategyManifest(name="greedy", display_name="Greedy", params={})
        strategy = m.create_strategy()
        assert strategy.name == "greedy"

    def test_create_strategy_with_params(self):
        m = StrategyManifest(name="mcts", display_name="MCTS", params={"iterations": 100})
        strategy = m.create_strategy()
        assert strategy.name == "mcts"


class TestImprovementAction:
    """改进建议"""

    def test_to_dict_from_dict(self):
        a = ImprovementAction(
            target_param="iterations",
            current_value=500,
            suggested_value=1000,
            reason="胜率过低",
            expected_impact="提升搜索深度",
            priority="high",
        )
        d = a.to_dict()
        a2 = ImprovementAction.from_dict(d)
        assert a2.target_param == "iterations"
        assert a2.suggested_value == 1000
        assert a2.priority == "high"


class TestIterationRecord:
    """迭代记录"""

    def test_create(self):
        rec = IterationRecord(iteration_id=1)
        assert rec.iteration_id == 1

    def test_to_dict_from_dict(self):
        manifest = StrategyManifest(name="mcts", display_name="MCTS", params={"iterations": 500})
        rec = IterationRecord(
            iteration_id=1,
            baseline_manifest=manifest,
            baseline_stats={"win_rate": 0.1},
            improvement_actions=[
                ImprovementAction("iterations", 500, 1000, "低胜率", "更深搜索", "high")
            ],
        )
        d = rec.to_dict()
        rec2 = IterationRecord.from_dict(d)
        assert rec2.iteration_id == 1
        assert rec2.baseline_manifest.name == "mcts"
        assert len(rec2.improvement_actions) == 1
        assert rec2.improvement_actions[0].suggested_value == 1000

    def test_save_load(self, tmp_path):
        rec = IterationRecord(iteration_id=1, baseline_stats={"win_rate": 0.1})
        path = rec.save(tmp_path / "iter_001.json")
        rec2 = IterationRecord.load(path)
        assert rec2.iteration_id == 1

    def test_summary(self):
        rec = IterationRecord(
            iteration_id=1,
            baseline_manifest=StrategyManifest(name="mcts", display_name="MCTS", params={}),
            baseline_stats={"win_rate": 0.05},
            improvement_actions=[
                ImprovementAction("iterations", 500, 1000, "低胜率", "更深搜索", "high")
            ],
            improved_stats={"win_rate": 0.15},
            delta={"win_rate": {"before": 0.05, "after": 0.15, "change": 0.1, "improved": True}},
        )
        summary = rec.summary()
        assert "迭代 #1" in summary
        assert "iterations" in summary


class TestIterationEngine:
    """迭代引擎"""

    def test_iterate(self, tmp_path):
        engine = IterationEngine(output_dir=str(tmp_path / "iter"))
        manifest = StrategyManifest(
            name="greedy",
            display_name="Greedy",
            params={},
        )
        record = engine.iterate(
            manifest=manifest,
            difficulty=1,
            num_games=3,
            max_moves=100,
        )
        assert record.iteration_id == 1
        assert record.baseline_stats is not None
        assert record.baseline_stats["total_games"] == 3

    def test_iterate_with_improvement(self, tmp_path):
        engine = IterationEngine(output_dir=str(tmp_path / "iter"))
        manifest = StrategyManifest(
            name="mcts_fast",
            display_name="MCTS Fast",
            params={"iterations": 100},
        )
        record = engine.iterate(
            manifest=manifest,
            difficulty=1,
            num_games=3,
            max_moves=100,
            auto_apply=True,
        )
        # 应该有改进建议（因为 iterations=100 很低）
        assert len(record.improvement_actions) > 0
        # 应该有改进后的评估
        assert record.improved_manifest is not None
        assert record.improved_stats is not None
        assert record.delta != {}

    def test_save_and_load_history(self, tmp_path):
        engine = IterationEngine(output_dir=str(tmp_path / "iter"))
        manifest = StrategyManifest(name="greedy", display_name="Greedy", params={})
        engine.iterate(manifest=manifest, difficulty=1, num_games=2, max_moves=100, auto_apply=False)
        engine.iterate(manifest=manifest, difficulty=1, num_games=2, max_moves=100, auto_apply=False)

        history = engine.load_history()
        assert len(history) == 2

    def test_evolution_summary(self, tmp_path):
        engine = IterationEngine(output_dir=str(tmp_path / "iter"))
        manifest = StrategyManifest(name="greedy", display_name="Greedy", params={})
        engine.iterate(manifest=manifest, difficulty=1, num_games=2, max_moves=100, auto_apply=False)

        summary = engine.evolution_summary()
        assert "策略进化摘要" in summary

    def test_load_manifests(self, tmp_path):
        engine = IterationEngine(output_dir=str(tmp_path / "iter"))
        manifest = StrategyManifest(name="mcts_fast", display_name="MCTS Fast", params={"iterations": 100})
        engine.iterate(manifest=manifest, difficulty=1, num_games=2, max_moves=100, auto_apply=True)

        manifests = engine.load_manifests()
        assert len(manifests) >= 1


class TestRegisterFromConfig:
    """注册中心配置加载"""

    def test_register_from_config(self):
        from src.strategy.registry import register_from_config, get_strategy
        register_from_config("test_mcts_v2", "mcts", {"iterations": 200})
        strategy = get_strategy("test_mcts_v2")
        assert strategy.name == "mcts"
        # 清理
        from src.strategy.registry import _REGISTRY
        _REGISTRY.pop("test_mcts_v2", None)
