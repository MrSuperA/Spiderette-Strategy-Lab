"""
策略迭代引擎 — 连接评估→分析→改进→对比的完整闭环
这是策略研究平台的核心编排器

设计原则：
  1. 每次迭代产生可序列化、可比较的完整记录
  2. 分析结果必须可直接转化为策略参数调整
  3. 训练产物必须可保存、可加载、可跨版本比较
  4. 整个流程可一键执行，也可逐步控制
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from src.utils.logging import get_logger
_logger = get_logger(__name__)
from typing import Optional

from src.analysis.metrics import StrategyStats, collect_stats, compare_strategies
from src.analysis.utils import run_games_batch
from src.core.manifest import StrategyManifest, ImprovementAction, IterationRecord
from src.core.session import GameResult
from src.core.types import Strategy




# ═══════════════════════════════════════════════════════════
#  迭代引擎 — 编排评估→分析→改进→对比
# ═══════════════════════════════════════════════════════════

class IterationEngine:
    """
    策略迭代引擎

    一键执行完整迭代流程：
      评估基线 → 分析弱点 → 生成改进 → 应用改进 → 评估改进 → 对比

    用法::

        engine = IterationEngine(output_dir="iterations")
        record = engine.iterate(
            manifest=StrategyManifest(name="mcts", params={"iterations": 500}),
            difficulty=1,
            num_games=50,
        )
        _logger.info("迭代记录:
%s", record.summary())
    """

    def __init__(self, output_dir: str = "iterations"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._iteration_count = self._count_existing()

    def _count_existing(self) -> int:
        """统计已有迭代记录数"""
        count = 0
        for f in self._output_dir.glob("iteration_*.json"):
            try:
                int(f.stem.split("_")[1])
                count += 1
            except (ValueError, IndexError):
                pass
        return count

    def iterate(
        self,
        manifest: StrategyManifest,
        difficulty: int = 1,
        num_games: int = 50,
        max_moves: int = 500,
        auto_apply: bool = True,
        on_progress: Optional[callable] = None,
    ) -> IterationRecord:
        """
        执行一次完整迭代

        Args:
            manifest: 当前策略清单
            difficulty: 评估难度
            num_games: 评估局数
            max_moves: 每局最大步数
            auto_apply: 是否自动应用改进建议
            on_progress: 进度回调

        Returns:
            IterationRecord 完整迭代记录
        """
        self._iteration_count += 1
        record = IterationRecord(
            iteration_id=self._iteration_count,
            timestamp=datetime.now().isoformat(),
        )

        # ── Step 1: 评估基线 ──
        if on_progress:
            on_progress({"phase": "evaluate_baseline", "progress": 0.1})

        strategy = manifest.create_strategy()
        seeds = list(range(1, num_games + 1))
        baseline_results = run_games_batch(
            strategy, seeds, difficulty, max_moves,
            strategy_name=manifest.name,
        )
        baseline_stats_obj = collect_stats(manifest.name, baseline_results)
        record.baseline_manifest = manifest
        record.baseline_stats = baseline_stats_obj.to_dict()

        # ── Step 2: 分析弱点 ──
        if on_progress:
            on_progress({"phase": "analyze_weaknesses", "progress": 0.4})

        actions = self._analyze_and_suggest(manifest, baseline_stats_obj, difficulty)
        record.improvement_actions = actions

        # ── Step 3: 应用改进并评估 ──
        if auto_apply and actions:
            if on_progress:
                on_progress({"phase": "apply_improvements", "progress": 0.6})

            improved_manifest = self._apply_actions(manifest, actions)
            improved_strategy = improved_manifest.create_strategy()
            improved_results = run_games_batch(
                improved_strategy, seeds, difficulty, max_moves,
                strategy_name=improved_manifest.name,
            )
            improved_stats_obj = collect_stats(improved_manifest.name, improved_results)
            record.improved_manifest = improved_manifest
            record.improved_stats = improved_stats_obj.to_dict()

            # ── Step 4: 计算变化量 ──
            record.delta = self._compute_delta(
                record.baseline_stats, record.improved_stats
            )

            # 保存改进后的策略清单
            improved_manifest.metrics = record.improved_stats
            improved_manifest.save(
                self._output_dir / f"manifest_{improved_manifest.name}_v{improved_manifest.version}.json"
            )

        # ── Step 5: 保存迭代记录 ──
        record.save(self._output_dir / f"iteration_{record.iteration_id:03d}.json")

        if on_progress:
            on_progress({"phase": "done", "progress": 1.0})

        return record

    def _analyze_and_suggest(
        self,
        manifest: StrategyManifest,
        stats: StrategyStats,
        difficulty: int,
    ) -> list[ImprovementAction]:
        """基于评估结果生成具体的改进建议"""
        actions = []

        # 规则 1: 胜率过低 → 增加搜索深度
        if stats.win_rate < 0.1 and manifest.name in ("mcts", "mcts_fast", "mcts_deep", "is_mcts", "puct"):
            current_iter = manifest.params.get("iterations", 1000)
            suggested = min(current_iter * 2, 5000)
            if suggested > current_iter:
                actions.append(ImprovementAction(
                    target_param="iterations",
                    current_value=current_iter,
                    suggested_value=suggested,
                    reason=f"胜率 {stats.win_rate:.1%} 过低，增加搜索迭代次数",
                    expected_impact="提升搜索深度，发现更好的移动序列",
                    priority="high",
                ))

        # 规则 2: 胜率过低 → 增加探索权重
        if stats.win_rate < 0.15 and manifest.name in ("mcts", "mcts_fast", "mcts_deep"):
            current_exp = manifest.params.get("exploration", 1.4)
            if current_exp < 2.0:
                actions.append(ImprovementAction(
                    target_param="exploration",
                    current_value=current_exp,
                    suggested_value=min(current_exp + 0.3, 2.5),
                    reason="探索不足，可能陷入局部最优",
                    expected_impact="增加搜索多样性，发现更优策略路径",
                    priority="medium",
                ))

        # 规则 3: PUCT 的 c_puct 调整
        if stats.win_rate < 0.15 and manifest.name == "puct":
            current_cpuct = manifest.params.get("c_puct", 1.5)
            actions.append(ImprovementAction(
                target_param="c_puct",
                current_value=current_cpuct,
                suggested_value=min(current_cpuct + 0.5, 3.0),
                reason="PUCT 探索常数偏低",
                expected_impact="增强先验引导的探索力度",
                priority="medium",
            ))

        # 规则 4: IS-MCTS 确定化采样数
        if stats.win_rate < 0.1 and manifest.name == "is_mcts":
            current_ndet = manifest.params.get("n_determinizations", 10)
            if current_ndet < 20:
                actions.append(ImprovementAction(
                    target_param="n_determinizations",
                    current_value=current_ndet,
                    suggested_value=min(current_ndet + 5, 30),
                    reason="确定化采样不足，暗牌估计方差大",
                    expected_impact="降低信息不确定性，提高决策质量",
                    priority="medium",
                ))

        # 规则 5: 平均完成数低 → 调整启发式权重
        if stats.avg_completed < 3.0:
            actions.append(ImprovementAction(
                target_param="_hint_heuristic",
                current_value="当前启发式权重",
                suggested_value="考虑增加 same_suit_seq 权重",
                reason=f"平均完成 {stats.avg_completed:.1f}/8 序列，序列构建能力不足",
                expected_impact="引导策略更积极地构建同花色序列",
                priority="low",
            ))

        # 规则 6: 效率低（步数多但完成少）
        if stats.avg_moves > 200 and stats.avg_completed < 4:
            if manifest.name in ("mcts", "is_mcts", "puct"):
                current_td = manifest.params.get("time_limit", 1.0)
                actions.append(ImprovementAction(
                    target_param="time_limit",
                    current_value=current_td,
                    suggested_value=min(current_td + 0.5, 3.0),
                    reason=f"步数多({stats.avg_moves:.0f})但完成少({stats.avg_completed:.1f})，搜索质量不足",
                    expected_impact="延长搜索时间，提高每步决策质量",
                    priority="medium",
                ))

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        actions.sort(key=lambda a: priority_order.get(a.priority, 9))

        return actions

    def _apply_actions(
        self,
        baseline: StrategyManifest,
        actions: list[ImprovementAction],
    ) -> StrategyManifest:
        """应用改进建议，生成新的策略清单"""
        new_params = dict(baseline.params)
        applied_notes = []

        for action in actions:
            if action.target_param.startswith("_hint_"):
                # 提示性建议，不自动应用
                applied_notes.append(f"[提示] {action.reason}")
                continue
            if isinstance(action.suggested_value, (int, float)):
                new_params[action.target_param] = action.suggested_value
                applied_notes.append(
                    f"{action.target_param}: {action.current_value} → {action.suggested_value}"
                )

        # 递增版本号
        parts = baseline.version.split(".")
        new_version = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"

        return StrategyManifest(
            name=baseline.name,
            display_name=f"{baseline.display_name} (iter {self._iteration_count})",
            params=new_params,
            version=new_version,
            source="iteration",
            parent_version=baseline.version,
            notes="; ".join(applied_notes) if applied_notes else "无参数变更",
        )

    def _compute_delta(self, baseline: dict, improved: dict) -> dict:
        """计算关键指标的变化量"""
        delta = {}
        for key in ("win_rate", "avg_moves", "avg_completed", "avg_move_efficiency"):
            b = baseline.get(key, 0)
            i = improved.get(key, 0)
            if isinstance(b, (int, float)) and isinstance(i, (int, float)):
                d = i - b
                delta[key] = {
                    "before": round(b, 4),
                    "after": round(i, 4),
                    "change": round(d, 4),
                    "improved": d > 0 if key != "avg_moves" else d < 0,
                }
        return delta

    def load_history(self) -> list[IterationRecord]:
        """加载所有迭代历史"""
        records = []
        for f in sorted(self._output_dir.glob("iteration_*.json")):
            try:
                records.append(IterationRecord.load(f))
            except Exception:
                continue
        return records

    def load_manifests(self) -> list[StrategyManifest]:
        """加载所有策略清单"""
        manifests = []
        for f in sorted(self._output_dir.glob("manifest_*.json")):
            try:
                manifests.append(StrategyManifest.load(f))
            except Exception:
                continue
        return manifests

    def get_latest_manifest(self, strategy_name: str) -> Optional[StrategyManifest]:
        """获取某策略的最新版本清单"""
        manifests = [
            m for m in self.load_manifests()
            if m.name == strategy_name
        ]
        return manifests[-1] if manifests else None

    def evolution_summary(self) -> str:
        """生成策略进化摘要"""
        records = self.load_history()
        if not records:
            return "无迭代记录"

        lines = ["═══ 策略进化摘要 ═══"]
        for rec in records:
            lines.append(rec.summary())
            lines.append("")

        # 趋势分析
        win_rates = []
        for rec in records:
            if rec.improved_stats:
                win_rates.append(rec.improved_stats.get("win_rate", 0))
            elif rec.baseline_stats:
                win_rates.append(rec.baseline_stats.get("win_rate", 0))

        if len(win_rates) >= 2:
            lines.append("── 胜率趋势 ──")
            for i, wr in enumerate(win_rates):
                bar = "█" * int(wr * 20) + "░" * (20 - int(wr * 20))
                lines.append(f"  迭代 {i+1}: {bar} {wr:.1%}")

        return "\n".join(lines)
