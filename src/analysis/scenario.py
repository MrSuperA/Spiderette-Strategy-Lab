"""
标准化场景库 + 决策采集器
场景库：从大量游戏中提取决策点，构建可复现的标准化测试集
采集器：记录策略在每个场景上的决策，用于因子分析
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.types import GameState, Move, Rules, Strategy
from src.core.rules import RulesEngine
from src.core.session import GameSession
from src.envs.simulator import SimulatorEnv


# ═══════════════════════════════════════════════════════════
#  场景定义
# ═══════════════════════════════════════════════════════════

@dataclass
class DecisionScenario:
    """一个标准化决策场景"""
    scenario_id: str
    state: GameState
    legal_moves: list[Move]
    difficulty: int
    source_seed: int
    move_index: int                # 该局的第几步

    # 场景特征标注
    n_empty_cols: int = 0
    n_face_down: int = 0
    n_face_up: int = 0
    stock_remaining: int = 0
    completed: int = 0
    avg_sequence_length: float = 0.0

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "difficulty": self.difficulty,
            "source_seed": self.source_seed,
            "move_index": self.move_index,
            "n_legal_moves": len(self.legal_moves),
            "n_empty_cols": self.n_empty_cols,
            "n_face_down": self.n_face_down,
            "n_face_up": self.n_face_up,
            "stock_remaining": self.stock_remaining,
            "completed": self.completed,
            "avg_sequence_length": round(self.avg_sequence_length, 2),
        }


@dataclass
class ScenarioResponse:
    """策略在一个场景上的决策响应"""
    scenario_id: str
    strategy_name: str
    chosen_move_index: int         # 选了第几个合法移动
    chosen_move: Move
    all_moves_count: int
    elapsed_ms: float

    # 决策特征
    preserves_suit: bool = False   # 是否保持花色
    exposes_card: bool = False     # 是否翻牌
    uses_empty_col: bool = False   # 是否用空列
    is_deal: bool = False          # 是否发牌
    sequence_length: int = 0       # 移动的序列长度

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "strategy": self.strategy_name,
            "chosen_index": self.chosen_move_index,
            "all_moves": self.all_moves_count,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "preserves_suit": self.preserves_suit,
            "exposes_card": self.exposes_card,
            "uses_empty_col": self.uses_empty_col,
            "is_deal": self.is_deal,
            "sequence_length": self.sequence_length,
        }


# ═══════════════════════════════════════════════════════════
#  场景库
# ═══════════════════════════════════════════════════════════

class ScenarioLibrary:
    """
    标准化场景库

    构建流程：
    1. 用多种策略玩游戏，收集决策点
    2. 标注每个决策点的特征
    3. 去重 + 采样，构建固定测试集
    """

    def __init__(self):
        self.scenarios: list[DecisionScenario] = []
        self.metadata: dict = {}

    def build(
        self,
        n_source_games: int = 100,
        max_scenarios: int = 500,
        difficulty: int = 1,
        seed: int = 42,
    ) -> None:
        """
        构建场景库

        Args:
            n_source_games: 源游戏数量
            max_scenarios: 最大场景数
            difficulty: 难度
            seed: 随机种子
        """
        rng = random.Random(seed)
        rules = RulesEngine()
        raw_scenarios: list[DecisionScenario] = []

        # 阶段 1: 用多种策略提取决策点
        from src.strategy.registry import get_strategy
        explorers = [
            (get_strategy("random"), 0.3),
            (get_strategy("greedy"), 0.5),
            (get_strategy("mcts"), 0.2),
        ]

        for game_idx in range(n_source_games):
            # 随机选择探索策略
            r = rng.random()
            cumulative = 0
            strategy = explorers[0][0]
            for s, prob in explorers:
                cumulative += prob
                if r <= cumulative:
                    strategy = s
                    break

            game_seed = rng.randint(0, 2**31)
            env = SimulatorEnv(seed=game_seed, difficulty=difficulty)

            # 收集每步决策点
            for step in GameSession(env, strategy, max_moves=200):
                state = step.state
                legal = rules.legal_moves(state)

                if len(legal) < 2:
                    continue  # 只有 0-1 个选项的场景无分析价值

                # 每局最多采样 5 个决策点
                if sum(1 for s in raw_scenarios if s.source_seed == game_seed) >= 5:
                    break

                scenario = self._build_scenario(
                    state=state,
                    legal_moves=legal,
                    difficulty=difficulty,
                    source_seed=game_seed,
                    move_index=step.step_index,
                    rules=rules,
                    scenario_id=f"S{len(raw_scenarios):05d}",
                )
                raw_scenarios.append(scenario)

        # 阶段 2: 去重 + 采样
        # 简单去重：按 (n_legal_moves, n_empty_cols, stock_remaining) 去重
        seen = set()
        unique = []
        for s in raw_scenarios:
            key = (len(s.legal_moves), s.n_empty_cols, s.stock_remaining, s.completed)
            if key not in seen:
                seen.add(key)
                unique.append(s)

        # 采样
        if len(unique) > max_scenarios:
            unique = rng.sample(unique, max_scenarios)

        self.scenarios = unique
        self.metadata = {
            "n_source_games": n_source_games,
            "difficulty": difficulty,
            "seed": seed,
            "total_extracted": len(raw_scenarios),
            "total_unique": len(unique),
            "built_at": datetime.now().isoformat(),
        }

    def _build_scenario(
        self,
        state: GameState,
        legal_moves: list[Move],
        difficulty: int,
        source_seed: int,
        move_index: int,
        rules: Rules,
        scenario_id: str,
    ) -> DecisionScenario:
        """构建单个场景"""
        cols = state.columns
        empty = sum(1 for c in cols if c.is_empty)
        face_down = sum(c.face_down_count for c in cols)
        face_up = sum(len([c for c in col.cards if c.face_up]) for col in cols)

        # 平均序列长度
        seq_lengths = []
        for col in cols:
            seq = 0
            cards = [c for c in col.cards if c.face_up]
            for i in range(len(cards) - 1, 0, -1):
                if cards[i].rank == cards[i-1].rank - 1 and cards[i].suit == cards[i-1].suit:
                    seq += 1
                else:
                    break
            if seq > 0:
                seq_lengths.append(seq + 1)
        avg_seq = sum(seq_lengths) / len(seq_lengths) if seq_lengths else 0

        return DecisionScenario(
            scenario_id=scenario_id,
            state=state,
            legal_moves=legal_moves,
            difficulty=difficulty,
            source_seed=source_seed,
            move_index=move_index,
            n_empty_cols=empty,
            n_face_down=face_down,
            n_face_up=face_up,
            stock_remaining=len(state.stock),
            completed=state.completed,
            avg_sequence_length=avg_seq,
        )

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "scenarios": [s.to_dict() for s in self.scenarios],
        }


# ═══════════════════════════════════════════════════════════
#  决策采集器
# ═══════════════════════════════════════════════════════════

class ResponseCollector:
    """
    决策采集器 — 记录策略在标准化场景上的选择

    核心思想：
    同一场景，不同策略会做出不同选择。
    通过比较选择差异，量化策略的"决策偏好"。
    """

    def __init__(self):
        self.responses: dict[str, list[ScenarioResponse]] = {}  # {strategy: [responses]}

    def collect(
        self,
        strategy: Strategy,
        scenarios: list[DecisionScenario],
    ) -> list[ScenarioResponse]:
        """
        采集策略在场景库上的决策

        Args:
            strategy: 策略实例
            scenarios: 场景列表

        Returns:
            响应列表
        """
        rules = RulesEngine()
        responses = []

        for scenario in scenarios:
            t0 = time.perf_counter()
            chosen = strategy.choose(scenario.state, rules)
            elapsed = (time.perf_counter() - t0) * 1000

            if chosen is None:
                # 策略选择发牌
                response = ScenarioResponse(
                    scenario_id=scenario.scenario_id,
                    strategy_name=strategy.name,
                    chosen_move_index=-1,
                    chosen_move=Move(src_col=-1, src_start=0, dst_col=-1),
                    all_moves_count=len(scenario.legal_moves),
                    elapsed_ms=elapsed,
                    is_deal=True,
                )
            else:
                # 找到选中的移动在合法列表中的索引
                chosen_idx = 0
                for i, m in enumerate(scenario.legal_moves):
                    if m.src_col == chosen.src_col and m.dst_col == chosen.dst_col and m.src_start == chosen.src_start:
                        chosen_idx = i
                        break

                # 分析决策特征
                preserves_suit = self._check_suit_preservation(chosen, scenario.state)
                exposes_card = self._check_exposes_card(chosen, scenario.state)
                uses_empty = chosen.dst_col >= 0 and len(scenario.state.columns[chosen.dst_col].cards) == 0

                response = ScenarioResponse(
                    scenario_id=scenario.scenario_id,
                    strategy_name=strategy.name,
                    chosen_move_index=chosen_idx,
                    chosen_move=chosen,
                    all_moves_count=len(scenario.legal_moves),
                    elapsed_ms=elapsed,
                    preserves_suit=preserves_suit,
                    exposes_card=exposes_card,
                    uses_empty_col=uses_empty,
                    is_deal=False,
                    sequence_length=chosen.card_count,
                )

            responses.append(response)

        self.responses[strategy.name] = responses
        return responses

    def _check_suit_preservation(self, move: Move, state: GameState) -> bool:
        """检查移动是否保持花色"""
        if move.is_deal or move.dst_col < 0:
            return False
        cols = state.columns
        if move.src_col >= len(cols) or move.dst_col >= len(cols):
            return False
        src_cards = cols[move.src_col].cards
        dst_cards = cols[move.dst_col].cards
        if not src_cards or not dst_cards:
            return False
        src_suit = src_cards[-1].suit
        dst_suit = dst_cards[-1].suit
        return src_suit == dst_suit

    def _check_exposes_card(self, move: Move, state: GameState) -> bool:
        """检查移动是否翻开暗牌"""
        if move.is_deal:
            return False
        if move.src_col < 0 or move.src_col >= len(state.columns):
            return False
        col = state.columns[move.src_col]
        return col.face_down_count > 0

    def get_response_matrix(self, strategy_name: str) -> dict:
        """获取响应矩阵（用于因子分析）"""
        responses = self.responses.get(strategy_name, [])
        if not responses:
            return {}

        features = {
            "preserves_suit": [],
            "exposes_card": [],
            "uses_empty_col": [],
            "sequence_length": [],
            "is_deal": [],
            "elapsed_ms": [],
            "chosen_position": [],  # 选了第几个选项（归一化）
        }

        for r in responses:
            features["preserves_suit"].append(1.0 if r.preserves_suit else 0.0)
            features["exposes_card"].append(1.0 if r.exposes_card else 0.0)
            features["uses_empty_col"].append(1.0 if r.uses_empty_col else 0.0)
            features["sequence_length"].append(float(r.sequence_length))
            features["is_deal"].append(1.0 if r.is_deal else 0.0)
            features["elapsed_ms"].append(r.elapsed_ms)
            features["chosen_position"].append(
                r.chosen_move_index / max(1, r.all_moves_count)
            )

        return {
            "strategy": strategy_name,
            "n_responses": len(responses),
            "features": {k: {
                "mean": round(sum(v) / len(v), 4) if v else 0,
                "std": round((sum((x - sum(v)/len(v))**2 for x in v) / max(1, len(v)-1))**0.5, 4) if len(v) > 1 else 0,
            } for k, v in features.items()},
        }

    def export(self, output_dir: str | Path) -> Path:
        """导出采集数据"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        data = {
            "export_time": datetime.now().isoformat(),
            "n_strategies": len(self.responses),
            "strategies": {
                name: {
                    "n_responses": len(resps),
                    "responses": [r.to_dict() for r in resps],
                    "matrix": self.get_response_matrix(name),
                }
                for name, resps in self.responses.items()
            },
        }
        path = out / f"responses_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
