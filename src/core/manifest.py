"""
策略清单与迭代记录 — 纯数据层，无业务依赖

迁移自 src/iteration/engine.py，解决循环依赖：
  strategy.registry → iteration.engine → analysis.utils → strategy.registry

迁移后依赖关系：
  strategy.registry → core.manifest（无环）
  iteration.engine  → core.manifest（无环）
  analysis.utils    → strategy.registry（无环）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════
#  策略清单（Strategy Manifest）
# ═══════════════════════════════════════════════════════════

@dataclass
class StrategyManifest:
    """
    策略清单 — 一个策略的完整可序列化描述

    用途：
    - 保存训练/调优后的策略参数
    - 加载为可用的策略实例
    - 跨版本比较策略配置
    """
    name: str                    # 策略注册名（如 "mcts"）
    display_name: str            # 显示名
    params: dict = field(default_factory=dict)  # 构造参数
    base_strategy: str = ""  # 基础策略名（如 "mcts"），空则与 name 相同
    version: str = "1.0.0"
    created_at: str = ""
    source: str = ""             # "manual" / "genetic" / "tuning" / "training"
    parent_version: str = ""     # 上一版本（用于迭代链追踪）
    notes: str = ""
    metrics: dict = field(default_factory=dict)  # 评估指标快照

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "params": self.params,
            "base_strategy": self.base_strategy,
            "version": self.version,
            "created_at": self.created_at or datetime.now().isoformat(),
            "source": self.source,
            "parent_version": self.parent_version,
            "notes": self.notes,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StrategyManifest:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def save(self, path: str | Path) -> Path:
        """保存为 JSON 文件"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> StrategyManifest:
        """从 JSON 文件加载"""
        p = Path(path)
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))

    def create_strategy(self):
        """创建策略实例（延迟导入避免循环）"""
        from src.strategy.registry import get_strategy
        return get_strategy(self.name, **self.params)


# ═══════════════════════════════════════════════════════════
#  改进建议
# ═══════════════════════════════════════════════════════════

@dataclass
class ImprovementAction:
    """一个具体的改进建议（可直接执行）"""
    target_param: str            # 要调整的参数名
    current_value: Any           # 当前值
    suggested_value: Any         # 建议值
    reason: str                  # 原因（来自弱点检测/因子分析）
    expected_impact: str         # 预期影响
    priority: str = "medium"     # "high" / "medium" / "low"

    def to_dict(self) -> dict:
        return {
            "target_param": self.target_param,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "reason": self.reason,
            "expected_impact": self.expected_impact,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ImprovementAction:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════
#  迭代记录
# ═══════════════════════════════════════════════════════════

@dataclass
class IterationRecord:
    """
    一次迭代的完整记录

    包含：
    - 迭代前的策略清单和评估结果
    - 分析发现的弱点和改进建议
    - 应用改进后的策略清单和评估结果
    - 前后对比数据
    """
    iteration_id: int
    timestamp: str = ""

    # 迭代前
    baseline_manifest: Optional[StrategyManifest] = None
    baseline_stats: Optional[dict] = None

    # 分析结果
    weaknesses: list[dict] = field(default_factory=list)
    improvement_actions: list[ImprovementAction] = field(default_factory=list)
    factor_scores: dict = field(default_factory=dict)

    # 迭代后
    improved_manifest: Optional[StrategyManifest] = None
    improved_stats: Optional[dict] = None

    # 对比
    delta: dict = field(default_factory=dict)  # key 指标的变化量

    def to_dict(self) -> dict:
        return {
            "iteration_id": self.iteration_id,
            "timestamp": self.timestamp or datetime.now().isoformat(),
            "baseline_manifest": self.baseline_manifest.to_dict() if self.baseline_manifest else None,
            "baseline_stats": self.baseline_stats,
            "weaknesses": self.weaknesses,
            "improvement_actions": [a.to_dict() for a in self.improvement_actions],
            "factor_scores": self.factor_scores,
            "improved_manifest": self.improved_manifest.to_dict() if self.improved_manifest else None,
            "improved_stats": self.improved_stats,
            "delta": self.delta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> IterationRecord:
        rec = cls(
            iteration_id=d["iteration_id"],
            timestamp=d.get("timestamp", ""),
            baseline_stats=d.get("baseline_stats"),
            weaknesses=d.get("weaknesses", []),
            factor_scores=d.get("factor_scores", {}),
            improved_stats=d.get("improved_stats", {}),
            delta=d.get("delta", {}),
        )
        if d.get("baseline_manifest"):
            rec.baseline_manifest = StrategyManifest.from_dict(d["baseline_manifest"])
        if d.get("improved_manifest"):
            rec.improved_manifest = StrategyManifest.from_dict(d["improved_manifest"])
        if d.get("improvement_actions"):
            rec.improvement_actions = [ImprovementAction.from_dict(a) for a in d["improvement_actions"]]
        return rec

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> IterationRecord:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def summary(self) -> str:
        """生成人类可读的迭代摘要"""
        lines = [f"═══ 迭代 #{self.iteration_id} {'═' * 40}"]
        if self.baseline_manifest:
            lines.append(f"  基线: {self.baseline_manifest.display_name} v{self.baseline_manifest.version}")
        if self.baseline_stats:
            lines.append(f"  基线胜率: {self.baseline_stats.get('win_rate', 'N/A')}")
        if self.improvement_actions:
            lines.append(f"  改进项: {len(self.improvement_actions)} 个")
            for a in self.improvement_actions:
                lines.append(f"    [{a.priority}] {a.target_param}: {a.current_value} → {a.suggested_value}")
                lines.append(f"           原因: {a.reason}")
        if self.improved_manifest:
            lines.append(f"  改进后: {self.improved_manifest.display_name} v{self.improved_manifest.version}")
        if self.improved_stats:
            lines.append(f"  改进后胜率: {self.improved_stats.get('win_rate', 'N/A')}")
        if self.delta:
            lines.append(f"  变化: {self.delta}")
        return "\n".join(lines)
