"""
Flask Web 服务 — 研究模式 + 实时可视化
设计原则：API 返回 JSON，前端独立文件，SSE 实时推送

路由按职责拆分为 5 个模块：
  - routes/game.py:     游戏控制
  - routes/analysis.py: 分析研究
  - routes/iteration.py: 迭代引擎
  - routes/export.py:   数据导出
  - routes/system.py:   系统状态
"""

from __future__ import annotations

import concurrent.futures
import queue
import threading
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify

from src.core.session import GameResult, GameSession
from src.core.types import GameState, Strategy
from src.envs.simulator import SimulatorEnv
from src.analysis.runner import ExperimentRunner
from src.utils.logging import get_logger
from src.utils.config import get_config

STATIC_DIR = Path(__file__).parent / "static"
_logger = get_logger(__name__)


class SpideretteUI:
    """Web UI 服务器"""

    def __init__(self, host: str | None = None, port: int | None = None):
        cfg = get_config()
        self.host = host or cfg.get("server", "host", "127.0.0.1")
        self.port = port or cfg.get("server", "port", 5679)
        self.app = Flask(__name__, static_folder=str(STATIC_DIR))
        self._env: Optional[SimulatorEnv] = None
        self._strategy: Optional[Strategy] = None
        self._session: Optional[GameSession] = None
        self._result: Optional[GameResult] = None
        self._running = False
        self._lock = threading.Lock()
        self._sse_queues: list[queue.Queue] = []
        self._step_log: list[dict] = []
        self._current_state: Optional[GameState] = None
        self._experiment_runner = ExperimentRunner()
        self._exporter = self._create_exporter()
        self._task_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._tasks: dict[str, dict] = {}
        self._setup_error_handler()
        self._setup_routes()

    def _create_exporter(self):
        from src.analysis.exporter import GameExporter
        return GameExporter()

    def _setup_error_handler(self) -> None:
        """全局错误处理器 — 所有未捕获异常统一返回 JSON"""

        @self.app.errorhandler(Exception)
        def handle_exception(e):
            _logger.error("全局异常: %s", e, exc_info=True)
            ui._broadcast_log("error", f"全局异常: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

        @self.app.errorhandler(404)
        def handle_404(e):
            ui._broadcast_log("warn", f"404 Not Found: {e.description if hasattr(e,'description') else ''}")
            return jsonify({"ok": False, "error": "Not Found"}), 404

        @self.app.errorhandler(405)
        def handle_405(e):
            ui._broadcast_log("warn", "405 Method Not Allowed")
            return jsonify({"ok": False, "error": "Method Not Allowed"}), 405

    def _setup_routes(self) -> None:
        """注册所有路由（委托给各路由模块）"""
        from src.ui.routes.game import register_game_routes
        from src.ui.routes.analysis import register_analysis_routes
        from src.ui.routes.iteration import register_iteration_routes
        from src.ui.routes.export import register_export_routes
        from src.ui.routes.system import register_system_routes

        register_game_routes(self.app, self)
        register_analysis_routes(self.app, self)
        register_iteration_routes(self.app, self)
        register_export_routes(self.app, self)
        register_system_routes(self.app, self)

    # ── 共享工具方法（供路由模块调用） ──

    def _get_strategy(self, name: str) -> Strategy:
        """获取策略实例（通过注册中心，缓存避免重复创建）"""
        cached = getattr(self, '_strategy_cache', None)
        if cached is None:
            self._strategy_cache = {}
            cached = self._strategy_cache
        if name not in cached:
            from src.strategy.registry import get_strategy
            cached[name] = get_strategy(name)
        return cached[name]

    def _on_auto_step(self, step_record) -> None:
        """自动运行时的步进回调 — 紧凑模式，不推完整 state"""
        self._current_state = step_record.state
        self._step_log.append(step_record.to_dict())
        move = step_record.move
        action = "move"
        src, dst, count = -1, -1, 0
        top_card = ""
        if move:
            if move.is_deal:
                action = "deal"
            else:
                src = move.src_col
                dst = move.dst_col
                count = move.card_count
                cols = step_record.state.columns
                if 0 <= dst < len(cols) and cols[dst].cards:
                    top = cols[dst].cards[-1]
                    top_card = f"{top.rank}{top.suit}"
        cols = step_record.state.columns
        empty = sum(1 for c in cols if c.is_empty)
        self._exporter.record_step(
            step=step_record.step_index,
            action=action,
            src_col=src,
            dst_col=dst,
            card_count=count,
            top_card=top_card,
            completed=step_record.state.completed,
            stock_remaining=len(step_record.state.stock),
            empty_cols=empty,
            elapsed_ms=step_record.elapsed_ms,
            legal_moves=step_record.legal_move_count,
        )
        # 策略统计
        strategy_stats = {}
        if hasattr(self, '_current_strategy'):
            s = self._current_strategy
            if hasattr(s, 'last_iterations'):
                strategy_stats = {
                    "iterations": s.last_iterations,
                    "tree_size": s.last_tree_size,
                    "memory_hit_rate": round(s.memory_hit_rate, 3),
                }
        # 序列号（丢包检测）
        seq = getattr(self, '_sse_seq', 0) + 1
        self._sse_seq = seq
        # 紧凑模式：运行中不推完整 state，只推摘要
        state_summary = {
            "completed": step_record.state.completed,
            "stock_remaining": len(step_record.state.stock),
            "move_count": step_record.state.move_count,
            "total_cards": step_record.state.total_cards,
            "face_down": sum(c.face_down_count for c in step_record.state.columns),
            "empty_cols": empty,
        }
        self._broadcast({
            "type": "auto_step",
            "seq": seq,
            "step": step_record.to_dict(),
            "state": state_summary,
            "strategy_stats": strategy_stats,
        })

    def _get_status(self) -> dict:
        """获取当前状态快照"""
        data = {
            "running": self._running,
            "has_env": self._env is not None,
            "state": self._current_state.to_dict() if self._current_state else None,
            "result": self._result.to_dict() if self._result else None,
            "step_count": len(self._step_log),
        }
        # 策略统计数据（复用当前运行的策略实例，不重新创建）
        strategy = getattr(self, '_current_strategy', None)
        if strategy and hasattr(strategy, 'last_iterations'):
            data["strategy_stats"] = {
                "iterations": strategy.last_iterations,
                "tree_size": strategy.last_tree_size,
                "memory_hit_rate": round(strategy.memory_hit_rate, 3),
            }
        return data

    def _broadcast(self, data: dict) -> None:
        """SSE 广播"""
        for q in self._sse_queues:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass

    def _broadcast_log(self, level: str, msg: str) -> None:
        """向前端推送日志条目"""
        self._broadcast({"type": "log", "level": level, "msg": msg, "source": "back"})

    def _broadcast_full_state(self, event_type: str, result: dict = None) -> None:
        """广播完整状态（暂停/结束时调用，含完整 state 供前端渲染牌局）"""
        # 同时推送一条日志
        if event_type == "auto_paused":
            self._broadcast_log("info", "模拟已暂停")
        elif event_type == "auto_done":
            self._broadcast_log("info", "模拟完成")
        seq = getattr(self, '_sse_seq', 0) + 1
        self._sse_seq = seq
        data = {
            "type": event_type,
            "_sse_seq": seq,
            "state": self._current_state.to_dict() if self._current_state else None,
        }
        if result:
            data["result"] = result
        self._broadcast(data)

    def _submit_background(self, task_id: str, fn, *args, **kwargs) -> str:
        """提交后台任务，立即返回 task_id"""
        self._tasks[task_id] = {"status": "running", "result": None, "error": None}

        def _run():
            try:
                result = fn(*args, **kwargs)
                self._tasks[task_id] = {"status": "done", "result": result, "error": None}
            except Exception as e:
                self._tasks[task_id] = {"status": "error", "result": None, "error": str(e)}

        self._task_executor.submit(_run)
        return task_id

    def _get_task_status(self, task_id: str) -> dict:
        """获取后台任务状态"""
        return self._tasks.get(task_id, {"status": "unknown", "result": None, "error": "任务不存在"})
