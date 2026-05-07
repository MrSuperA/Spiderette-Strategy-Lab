"""
牌局导出模块 — 完整牌局记录 + 量化策略分析
支持 JSON / CSV / TXT 多格式导出
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.analysis.metrics import compute_distribution, DistributionStats


@dataclass
class StepRecord:
    """单步记录（紧凑格式）"""
    step: int
    action: str           # "move" / "deal" / "complete"
    src_col: int = -1
    dst_col: int = -1
    card_count: int = 0
    top_card: str = ""    # "K♠" 格式
    completed: int = 0
    stock_remaining: int = 0
    empty_cols: int = 0
    elapsed_ms: float = 0.0
    legal_moves: int = 0
    board_snapshot: str = ""  # 紧凑文本快照

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "action": self.action,
            "src_col": self.src_col,
            "dst_col": self.dst_col,
            "card_count": self.card_count,
            "top_card": self.top_card,
            "completed": self.completed,
            "stock_remaining": self.stock_remaining,
            "empty_cols": self.empty_cols,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "legal_moves": self.legal_moves,
        }


@dataclass
class GameExportData:
    """一局完整导出数据"""
    seed: int
    difficulty: int
    strategy: str
    outcome: str                      # "win" / "deadlock"
    total_moves: int
    total_time_ms: float
    completed: int
    steps: list[StepRecord] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""

    @property
    def move_efficiency(self) -> float:
        return self.completed / self.total_moves if self.total_moves > 0 else 0.0

    @property
    def avg_step_ms(self) -> float:
        return self.total_time_ms / self.total_moves if self.total_moves > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "difficulty": self.difficulty,
            "strategy": self.strategy,
            "outcome": self.outcome,
            "total_moves": self.total_moves,
            "total_time_ms": round(self.total_time_ms, 2),
            "completed": self.completed,
            "move_efficiency": round(self.move_efficiency, 4),
            "avg_step_ms": round(self.avg_step_ms, 2),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "steps": [s.to_dict() for s in self.steps],
            "step_count": len(self.steps),
        }


class GameExporter:
    """牌局导出器"""

    def __init__(self):
        self._current: Optional[GameExportData] = None
        self._history: list[GameExportData] = []

    def start_game(self, seed: int, difficulty: int, strategy: str) -> None:
        """开始记录新牌局"""
        self._current = GameExportData(
            seed=seed,
            difficulty=difficulty,
            strategy=strategy,
            outcome="playing",
            total_moves=0,
            total_time_ms=0.0,
            completed=0,
            start_time=datetime.now().isoformat(),
        )

    def record_step(
        self,
        step: int,
        action: str,
        src_col: int = -1,
        dst_col: int = -1,
        card_count: int = 0,
        top_card: str = "",
        completed: int = 0,
        stock_remaining: int = 0,
        empty_cols: int = 0,
        elapsed_ms: float = 0.0,
        legal_moves: int = 0,
        board_snapshot: str = "",
    ) -> None:
        """记录单步"""
        if not self._current:
            return
        self._current.steps.append(StepRecord(
            step=step,
            action=action,
            src_col=src_col,
            dst_col=dst_col,
            card_count=card_count,
            top_card=top_card,
            completed=completed,
            stock_remaining=stock_remaining,
            empty_cols=empty_cols,
            elapsed_ms=elapsed_ms,
            legal_moves=legal_moves,
            board_snapshot=board_snapshot,
        ))

    def end_game(self, outcome: str, total_moves: int, total_time_ms: float, completed: int) -> None:
        """结束当前牌局"""
        if not self._current:
            return
        self._current.outcome = outcome
        self._current.total_moves = total_moves
        self._current.total_time_ms = total_time_ms
        self._current.completed = completed
        self._current.end_time = datetime.now().isoformat()
        self._history.append(self._current)
        self._current = None

    def get_current(self) -> Optional[dict]:
        """获取当前牌局数据"""
        return self._current.to_dict() if self._current else None

    def get_history(self) -> list[dict]:
        """获取历史牌局"""
        return [g.to_dict() for g in self._history]

    def export_json(self, output_dir: str | Path) -> Path:
        """导出 JSON（含策略量化分析）"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 按策略分组统计
        by_strategy: dict[str, list[GameExportData]] = {}
        for g in self._history:
            by_strategy.setdefault(g.strategy, []).append(g)

        strategy_analysis = {}
        for strat_name, games in by_strategy.items():
            wins = sum(1 for g in games if g.outcome == "win")
            moves = [g.total_moves for g in games]
            completed = [g.completed for g in games]
            efficiency = [g.move_efficiency for g in games]
            avg_step = [g.avg_step_ms for g in games]

            wstreak = lstreak = maxw = maxl = 0
            for g in games:
                if g.outcome == "win": wstreak += 1; lstreak = 0
                else: lstreak += 1; wstreak = 0
                maxw = max(maxw, wstreak); maxl = max(maxl, lstreak)

            moves_dist = compute_distribution(moves)
            completed_dist = compute_distribution(completed)
            efficiency_dist = compute_distribution(efficiency)
            step_dist = compute_distribution(avg_step)

            strategy_analysis[strat_name] = {
                "games": len(games),
                "wins": wins,
                "win_rate": round(wins / len(games), 4) if games else 0,
                "moves": {"mean": round(moves_dist.mean, 1), "std": round(moves_dist.std, 1), "median": round(moves_dist.median, 1), "p90": round(moves_dist.p90, 1)},
                "completed": {"mean": round(completed_dist.mean, 2), "std": round(completed_dist.std, 2)},
                "efficiency": {"mean": round(efficiency_dist.mean, 4), "std": round(efficiency_dist.std, 4)},
                "avg_step_ms": round(step_dist.mean, 2),
                "max_win_streak": maxw,
                "max_lose_streak": maxl,
            }

        data = {
            "export_time": datetime.now().isoformat(),
            "total_games": len(self._history),
            "strategy_analysis": strategy_analysis,
            "games": [g.to_dict() for g in self._history],
        }
        path = out / f"game_export_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def export_csv(self, output_dir: str | Path) -> Path:
        """导出 CSV（策略汇总 + 每步明细）"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 文件 1: 策略汇总
        summary_path = out / f"strategy_summary_{ts}.csv"
        by_strategy: dict[str, list[GameExportData]] = {}
        for g in self._history:
            by_strategy.setdefault(g.strategy, []).append(g)

        with open(summary_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "strategy", "games", "wins", "win_rate",
                "avg_moves", "std_moves", "median_moves", "p90_moves",
                "avg_completed", "std_completed",
                "avg_efficiency", "std_efficiency",
                "avg_step_ms", "max_win_streak", "max_lose_streak",
            ])
            for strat_name, games in by_strategy.items():
                wins = sum(1 for g in games if g.outcome == "win")
                moves = [g.total_moves for g in games]
                completed = [g.completed for g in games]
                efficiency = [g.move_efficiency for g in games]
                avg_step = [g.avg_step_ms for g in games]
                wstreak = lstreak = maxw = maxl = 0
                for g in games:
                    if g.outcome == "win": wstreak += 1; lstreak = 0
                    else: lstreak += 1; wstreak = 0
                    maxw = max(maxw, wstreak); maxl = max(maxl, lstreak)
                moves_dist = compute_distribution(moves)
                completed_dist = compute_distribution(completed)
                efficiency_dist = compute_distribution(efficiency)
                step_dist = compute_distribution(avg_step)
                writer.writerow([
                    strat_name, len(games), wins, round(wins/len(games), 4) if games else 0,
                    round(moves_dist.mean, 1), round(moves_dist.std, 1), round(moves_dist.median, 1), round(moves_dist.p90, 1),
                    round(completed_dist.mean, 2), round(completed_dist.std, 2),
                    round(efficiency_dist.mean, 4), round(efficiency_dist.std, 4),
                    round(step_dist.mean, 2), maxw, maxl,
                ])

        # 文件 2: 每步明细
        detail_path = out / f"step_detail_{ts}.csv"
        with open(detail_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "game", "seed", "difficulty", "strategy", "outcome",
                "step", "action", "src_col", "dst_col", "card_count",
                "top_card", "completed", "stock", "empty_cols",
                "elapsed_ms", "legal_moves",
            ])
            for gi, game in enumerate(self._history):
                for s in game.steps:
                    writer.writerow([
                        gi + 1, game.seed, game.difficulty, game.strategy, game.outcome,
                        s.step, s.action, s.src_col, s.dst_col, s.card_count,
                        s.top_card, s.completed, s.stock_remaining, s.empty_cols,
                        round(s.elapsed_ms, 2), s.legal_moves,
                    ])

        return detail_path

    def export_txt(self, output_dir: str | Path) -> Path:
        """导出可读文本报告（含策略量化分析）"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"game_export_{datetime.now():%Y%m%d_%H%M%S}.txt"
        lines = []
        lines.append("=" * 60)
        lines.append("  Spiderette Strategy Lab — 牌局导出报告")
        lines.append("=" * 60)
        lines.append(f"  导出时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
        lines.append(f"  总牌局数: {len(self._history)}")
        wins = sum(1 for g in self._history if g.outcome == "win")
        lines.append(f"  胜率: {wins}/{len(self._history)} ({wins/max(1,len(self._history))*100:.1f}%)")
        lines.append("")

        # ── 策略量化分析 ──
        if self._history:
            lines.append("── 策略量化分析 ──" + "─" * 40)
            lines.append("")
            # 按策略分组
            by_strategy: dict[str, list[GameExportData]] = {}
            for g in self._history:
                by_strategy.setdefault(g.strategy, []).append(g)

            for strat_name, games in by_strategy.items():
                sw = sum(1 for g in games if g.outcome == "win")
                sm = [g.total_moves for g in games]
                sc = [g.completed for g in games]
                se = [g.move_efficiency for g in games]
                sa = [g.avg_step_ms for g in games]

                moves_dist = compute_distribution(sm)
                completed_dist = compute_distribution(sc)
                efficiency_dist = compute_distribution(se)
                step_dist = compute_distribution(sa)

                lines.append(f"  策略: {strat_name}")
                lines.append(f"    局数: {len(games)}  胜率: {sw}/{len(games)} ({sw/len(games)*100:.1f}%)")
                lines.append(f"    步数: 均值={moves_dist.mean:.0f}  标准差={moves_dist.std:.1f}  中位数={moves_dist.median:.0f}  P90={moves_dist.p90:.0f}")
                lines.append(f"    完成: 均值={completed_dist.mean:.1f}/8  标准差={completed_dist.std:.1f}")
                lines.append(f"    效率: 均值={efficiency_dist.mean:.4f}  标准差={efficiency_dist.std:.4f}")
                lines.append(f"    步均耗时: 均值={step_dist.mean:.1f}ms")
                # 连胜/连败
                wstreak = lstreak = maxw = maxl = 0
                for g in games:
                    if g.outcome == "win": wstreak += 1; lstreak = 0
                    else: lstreak += 1; wstreak = 0
                    maxw = max(maxw, wstreak); maxl = max(maxl, lstreak)
                lines.append(f"    最长连胜: {maxw}  最长连败: {maxl}")
                lines.append("")

        # ── 牌局详情 ──
        for i, game in enumerate(self._history):
            lines.append(f"── 牌局 #{i+1} {'─' * 45}")
            lines.append(f"  种子: {game.seed}  难度: {game.difficulty}花色  策略: {game.strategy}")
            lines.append(f"  结果: {'胜利' if game.outcome=='win' else '死局'}  步数: {game.total_moves}  完成: {game.completed}/8")
            lines.append(f"  效率: {game.move_efficiency:.4f}  步均耗时: {game.avg_step_ms:.1f}ms")
            lines.append(f"  开始: {game.start_time}  结束: {game.end_time}")
            lines.append("")

            show_steps = game.steps[-30:] if len(game.steps) > 30 else game.steps
            if len(game.steps) > 30:
                lines.append(f"  ... 省略前 {len(game.steps)-30} 步 ...")
            lines.append(f"  {'#':>4} {'操作':<16} {'顶牌':<6} {'完成':>2} {'发牌':>3} {'空列':>2} {'耗时':>8} {'合法':>3}")
            lines.append(f"  {'─'*4} {'─'*16} {'─'*6} {'─'*2} {'─'*3} {'─'*2} {'─'*8} {'─'*3}")
            for s in show_steps:
                act = s.action
                if act == "deal": desc = "发牌"
                elif act == "complete": desc = "完成序列"
                elif s.src_col >= 0 and s.dst_col >= 0: desc = f"列{s.src_col+1}→列{s.dst_col+1} ({s.card_count}张)"
                else: desc = act
                lines.append(
                    f"  {s.step:>4} {desc:<16} {s.top_card:<6} "
                    f"{s.completed:>2} {s.stock_remaining:>3} {s.empty_cols:>2} "
                    f"{s.elapsed_ms:>7.1f}ms {s.legal_moves:>3}"
                )
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
