"""
game routes - extracted from server.py
"""
from __future__ import annotations
import threading
from flask import jsonify, request
from src.core.session import GameSession
from src.envs.simulator import SimulatorEnv
from src.utils.logging import get_logger
from src.utils.config import get_config

_logger = get_logger(__name__)


def register_game_routes(app, ui):
    """Register game routes"""
    cfg = get_config()

    @app.route("/api/new-game", methods=["POST"])
    def new_game():
        data = request.get_json(silent=True) or {}
        seed = data.get("seed", 0)
        difficulty = data.get("difficulty", cfg.get("analysis", "difficulty", 2))
        strategy = data.get("strategy", "mcts")
        with ui._lock:
            ui._env = SimulatorEnv(seed=seed, difficulty=difficulty)
            ui._current_state = ui._env.observe()
            ui._step_log.clear()
            ui._result = None
            ui._running = False
            ui._exporter.start_game(seed, difficulty, strategy)
        ui._broadcast({"type": "new_game", "state": ui._current_state.to_dict()})
        return jsonify({"ok": True, "state": ui._current_state.to_dict()})

    # 执行一步
    @app.route("/api/step", methods=["POST"])
    def step():
        with ui._lock:
            if not ui._env:
                return jsonify({"ok": False, "error": "未初始化"}), 400

            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "mcts")
            strategy = ui._get_strategy(strategy_name)

            session = GameSession(ui._env, strategy, max_moves=1)
            result = session.run()

            ui._current_state = ui._env.observe()
            step_data = {
                "type": "step",
                "state": ui._current_state.to_dict(),
                "result": result.to_dict(),
                "steps": [s.to_dict() for s in result.steps],
            }
            ui._step_log.append(step_data)
        ui._broadcast(step_data)
        return jsonify({"ok": True, **step_data})

    # 自动运行
    @app.route("/api/auto-play", methods=["POST"])
    def auto_play():
        if not ui._env:
            return jsonify({"ok": False, "error": "未初始化"}), 400

        data = request.get_json(silent=True) or {}
        strategy_name = data.get("strategy", "mcts")
        max_moves = data.get("max_moves", cfg.get("session", "max_moves", 500))
        strategy = ui._get_strategy(strategy_name)
        ui._current_strategy_name = strategy_name
        ui._current_strategy = strategy

        ui._running = True

        def _run():
            try:
                # 自适应步进延迟：简单策略快跑，复杂策略不阻塞
                delay = 0.05 if strategy_name in ("greedy", "random") else 0.1
                for step in GameSession(ui._env, strategy, max_moves=max_moves, step_delay=delay):
                    if not ui._running:
                        break
                    ui._on_auto_step(step)
            except Exception as e:
                _logger.error("自动运行异常: %s", e, exc_info=True)
            finally:
                was_running = ui._running
                ui._running = False
                ui._current_state = ui._env.observe()

                if ui._current_state:
                    outcome = ui._rules.is_terminal(ui._current_state)
                    is_real_end = outcome.name in ("WIN", "DEADLOCK")

                    if is_real_end:
                        # 真正的游戏结束
                        ui._exporter.end_game(
                            outcome=outcome.name.lower(),
                            total_moves=ui._current_state.move_count,
                            total_time_ms=0,
                            completed=ui._current_state.completed,
                        )
                        ui._broadcast_full_state("auto_done", {"outcome": outcome.name.lower()})
                    else:
                        # 暂停或停止（游戏未结束）
                        ui._broadcast_full_state("auto_paused")

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"ok": True, "message": "自动运行已启动"})

    # 停止自动运行
    @app.route("/api/stop", methods=["POST"])
    def stop():
        with ui._lock:
            ui._running = False
        return jsonify({"ok": True})

    # 策略列表（通过注册中心）
    @app.route("/api/replay")
    def replay():
        games = ui._exporter.get_history()
        if not games:
            return jsonify({"ok": False, "error": "无历史牌局"})
        idx = int(request.args.get("index", len(games) - 1))
        if 0 <= idx < len(games):
            return jsonify({"ok": True, "game": games[idx], "total": len(games)})
        return jsonify({"ok": False, "error": "索引越界"})

    # 策略热切换（实际更新运行中的策略实例）
    @app.route("/api/switch-strategy", methods=["POST"])
    def switch_strategy():
        data = request.get_json(silent=True) or {}
        new_name = data.get("strategy", "mcts")
        try:
            strategy = ui._get_strategy(new_name)
            ui._current_strategy = strategy
            ui._current_strategy_name = new_name
            return jsonify({"ok": True, "strategy": new_name})
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)})

    # 遗传算法优化（后台执行）

