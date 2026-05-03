"""
Flask Web 服务 — 研究模式 + 实时可视化
设计原则：API 返回 JSON，前端独立文件，SSE 实时推送
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, request, send_from_directory

from src.core.session import GameResult, GameSession
from src.core.types import GameState, Move, Strategy
from src.core.rules import RulesEngine
from src.envs.simulator import SimulatorEnv
from src.strategy.mcts import MCTSStrategy, create_mcts, create_mcts_deep, create_mcts_fast
from src.strategy.compose import GreedyStrategy, RandomStrategy, with_cache
from src.analysis.metrics import collect_stats, compare_strategies
from src.analysis.runner import ExperimentRunner
from src.utils.paths import get_output_dir, get_experiments_dir, get_iterations_dir, get_models_dir

STATIC_DIR = Path(__file__).parent / "static"


class SpideretteUI:
    """Web UI 服务器"""

    def __init__(self, host: str = "127.0.0.1", port: int = 5679):
        self.host = host
        self.port = port
        self.app = Flask(__name__, static_folder=str(STATIC_DIR))
        self._rules = RulesEngine()
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
        # 后台任务执行器（4 个并发线程，避免阻塞 Waitress 工作线程）
        self._task_executor = __import__('concurrent.futures').futures.ThreadPoolExecutor(max_workers=4)
        self._tasks: dict[str, dict] = {}  # task_id -> {"status", "result", "error"}
        self._setup_error_handler()
        self._setup_routes()

    def _create_exporter(self):
        from src.analysis.exporter import GameExporter
        return GameExporter()

    def _setup_error_handler(self) -> None:
        """全局错误处理器 — 所有未捕获异常统一返回 JSON"""

        @self.app.errorhandler(Exception)
        def handle_exception(e):
            import traceback
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(e)}), 500

        @self.app.errorhandler(404)
        def handle_404(e):
            return jsonify({"ok": False, "error": "Not Found"}), 404

        @self.app.errorhandler(405)
        def handle_405(e):
            return jsonify({"ok": False, "error": "Method Not Allowed"}), 405

    # ── 路由注册 ──

    def _setup_routes(self) -> None:
        app = self.app

        # 版本号
        @app.route("/api/version")
        def version():
            from src import __version__
            return jsonify({"version": __version__})

        # 静态文件
        @app.route("/")
        def index():
            return send_from_directory(str(STATIC_DIR), "index.html")

        @app.route("/static/<path:filename>")
        def static_files(filename):
            return send_from_directory(str(STATIC_DIR), filename)

        # SSE 实时推送
        @app.route("/api/stream")
        def stream():
            q: queue.Queue = queue.Queue()
            self._sse_queues.append(q)

            def generate():
                try:
                    while True:
                        try:
                            data = q.get(timeout=1.0)
                            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                        except queue.Empty:
                            yield ": keepalive\n\n"
                finally:
                    if q in self._sse_queues:
                        self._sse_queues.remove(q)

            return Response(generate(), mimetype="text/event-stream")

        # 状态查询
        @app.route("/api/status")
        def status():
            return jsonify(self._get_status())

        # 开始新牌局
        @app.route("/api/new-game", methods=["POST"])
        def new_game():
            data = request.get_json(silent=True) or {}
            seed = data.get("seed", 0)
            difficulty = data.get("difficulty", 2)
            strategy = data.get("strategy", "mcts")
            with self._lock:
                self._env = SimulatorEnv(seed=seed, difficulty=difficulty)
                self._current_state = self._env.observe()
                self._step_log.clear()
                self._result = None
                self._running = False
                self._exporter.start_game(seed, difficulty, strategy)
            self._broadcast({"type": "new_game", "state": self._current_state.to_dict()})
            return jsonify({"ok": True, "state": self._current_state.to_dict()})

        # 执行一步
        @app.route("/api/step", methods=["POST"])
        def step():
            with self._lock:
                if not self._env:
                    return jsonify({"ok": False, "error": "未初始化"}), 400

                data = request.get_json(silent=True) or {}
                strategy_name = data.get("strategy", "mcts")
                strategy = self._get_strategy(strategy_name)

                session = GameSession(self._env, strategy, max_moves=1)
                result = session.run()

                self._current_state = self._env.observe()
                step_data = {
                    "type": "step",
                    "state": self._current_state.to_dict(),
                    "result": result.to_dict(),
                    "steps": [s.to_dict() for s in result.steps],
                }
                self._step_log.append(step_data)
            self._broadcast(step_data)
            return jsonify({"ok": True, **step_data})

        # 自动运行
        @app.route("/api/auto-play", methods=["POST"])
        def auto_play():
            if not self._env:
                return jsonify({"ok": False, "error": "未初始化"}), 400

            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "mcts")
            max_moves = data.get("max_moves", 200)
            strategy = self._get_strategy(strategy_name)
            self._current_strategy_name = strategy_name
            self._current_strategy = strategy

            self._running = True

            def _run():
                try:
                    for step in GameSession(self._env, strategy, max_moves=max_moves, step_delay=0.5):
                        if not self._running:
                            break
                        self._on_auto_step(step)
                except Exception as e:
                    print(f"[错误] 自动运行异常: {e}")
                finally:
                    was_running = self._running
                    self._running = False
                    self._current_state = self._env.observe()

                    if self._current_state:
                        outcome = self._rules.is_terminal(self._current_state)
                        is_real_end = outcome.name in ("WIN", "DEADLOCK")

                        if is_real_end:
                            # 真正的游戏结束
                            self._exporter.end_game(
                                outcome=outcome.name.lower(),
                                total_moves=self._current_state.move_count,
                                total_time_ms=0,
                                completed=self._current_state.completed,
                            )
                            self._broadcast({
                                "type": "auto_done",
                                "result": {"outcome": outcome.name.lower()},
                                "state": self._current_state.to_dict(),
                            })
                        else:
                            # 暂停或停止（游戏未结束）
                            self._broadcast({
                                "type": "auto_paused",
                                "state": self._current_state.to_dict(),
                            })

            threading.Thread(target=_run, daemon=True).start()
            return jsonify({"ok": True, "message": "自动运行已启动"})

        # 停止自动运行
        @app.route("/api/stop", methods=["POST"])
        def stop():
            with self._lock:
                self._running = False
            return jsonify({"ok": True})

        # 策略列表（通过注册中心）
        @app.route("/api/strategies")
        def strategies():
            from src.strategy.registry import list_strategies
            return jsonify({"strategies": list_strategies()})

        # 多策略对比（后台执行）
        @app.route("/api/compare", methods=["POST"])
        def compare_strategies_endpoint():
            import uuid
            data = request.get_json(silent=True) or {}
            strategy_names = data.get("strategies", ["greedy", "mcts"])
            difficulty = data.get("difficulty", 1)
            num_games = min(data.get("num_games", 10), 50)
            task_id = f"compare_{uuid.uuid4().hex[:8]}"

            def _run():
                from src.analysis.compare import ParallelStrategyRunner
                runner = ParallelStrategyRunner()
                report = runner.compare(
                    strategy_names=strategy_names,
                    difficulty=difficulty,
                    seeds=list(range(1, num_games + 1)),
                    parallel=False,
                )
                return report.to_dict()

            self._submit_background(task_id, _run)
            return jsonify({"ok": True, "task_id": task_id})

        # 弱点检测
        @app.route("/api/weakness", methods=["POST"])
        def detect_weakness():
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "greedy")
            factors = data.get("factors", {})
            try:
                from src.analysis.weakness import detect_weaknesses
                report = detect_weaknesses(strategy_name, factors)
                return jsonify({"ok": True, **report.to_dict()})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        # 牌局导出
        @app.route("/api/export", methods=["POST"])
        def export_game():
            data = request.get_json(silent=True) or {}
            fmt = data.get("format", "json")
            try:
                out_dir = get_experiments_dir()
                if fmt == "json":
                    path = self._exporter.export_json(out_dir)
                elif fmt == "csv":
                    path = self._exporter.export_csv(out_dir)
                else:
                    path = self._exporter.export_txt(out_dir)
                return jsonify({"ok": True, "path": str(path), "format": fmt})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.route("/api/export/history")
        def export_history():
            return jsonify({"ok": True, "games": self._exporter.get_history()})

        # 策略量化导出
        @app.route("/api/export/profile", methods=["POST"])
        def export_profile():
            data = request.get_json(silent=True) or {}
            fmt = data.get("format", "json")
            try:
                from src.analysis.profile import (
                    StrategyProfileExporter, StrategyQuantitativeProfile,
                    StrategyIdentity, SearchBehavior, PerformanceMetrics,
                    DistributionMetric,
                )
                from src.analysis.metrics import collect_stats

                exporter = StrategyProfileExporter()

                # 为每个策略生成量化档案
                strategies = data.get("strategies", ["greedy", "mcts"])
                difficulty = data.get("difficulty", 1)
                num_games = min(data.get("num_games", 20), 100)

                for strat_name in strategies:
                    strategy = self._get_strategy(strat_name)
                    results = []
                    for seed in range(1, num_games + 1):
                        env = SimulatorEnv(seed=seed, difficulty=difficulty)
                        session = GameSession(env, strategy, max_moves=500)
                        result = session.run()
                        results.append(result)

                    stats = collect_stats(strat_name, results)

                    # 构建量化档案
                    profile = StrategyQuantitativeProfile(
                        identity=StrategyIdentity(
                            name=strat_name,
                            display_name=strat_name,
                            parameters={"difficulty": difficulty, "num_games": num_games},
                        ),
                        performance=[PerformanceMetrics(
                            difficulty=difficulty,
                            n_games=stats.total_games,
                            wins=stats.wins,
                            win_rate=stats.win_rate,
                            win_rate_ci=stats.win_rate_ci95,
                            moves=DistributionMetric(
                                mean=stats.moves_distribution.mean,
                                std=stats.moves_distribution.std,
                                median=stats.moves_distribution.median,
                                p25=stats.moves_distribution.p25,
                                p75=stats.moves_distribution.p75,
                                p90=stats.moves_distribution.p90,
                                min_val=stats.moves_distribution.min_val,
                                max_val=stats.moves_distribution.max_val,
                            ),
                            completed=DistributionMetric(
                                mean=stats.completed_distribution.mean,
                                std=stats.completed_distribution.std,
                                median=stats.completed_distribution.median,
                            ),
                            efficiency=DistributionMetric(
                                mean=stats.avg_move_efficiency,
                            ),
                            avg_step_ms=stats.avg_time_ms,
                            max_win_streak=stats.max_win_streak,
                            max_lose_streak=stats.max_lose_streak,
                        )],
                        n_scenarios_used=num_games,
                        engine_version="1.0.0",
                    )
                    exporter.add_profile(profile)

                out_dir = get_experiments_dir()
                if fmt == "json":
                    path = exporter.export_json(out_dir)
                else:
                    path = exporter.export_txt(out_dir)
                return jsonify({"ok": True, "path": str(path), "format": fmt})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        # ── 后台任务状态查询 ──

        @app.route("/api/task/<task_id>")
        def get_task_status(task_id):
            status = self._get_task_status(task_id)
            return jsonify({"ok": True, **status})

        # 策略量化因子计算（后台执行，避免阻塞 Waitress 线程）
        @app.route("/api/calc-factors", methods=["POST"])
        def calc_factors():
            import uuid
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "greedy")
            difficulty = data.get("difficulty", 1)
            num_games = min(data.get("num_games", 10), 50)

            task_id = f"factors_{uuid.uuid4().hex[:8]}"

            def _compute():
                strategy = self._get_strategy(strategy_name)
                total_moves = 0
                same_suit_moves = 0
                expose_moves = 0
                deal_moves = 0
                deal_when_movable = 0
                total_deals = 0
                use_empty_moves = 0
                empty_available = 0
                non_reversible = 0
                destructive_moves = 0
                choices_per_state: list[int] = []

                for seed in range(1, num_games + 1):
                    env = SimulatorEnv(seed=seed, difficulty=difficulty)
                    rules = env.rules
                    prev_cols = None

                    for step in GameSession(env, strategy, max_moves=300):
                        state = step.state
                        move = step.move
                        legal = rules.legal_moves(state)

                        if move and not move.is_deal:
                            total_moves += 1
                            cols = state.columns
                            src = move.src_col
                            dst = move.dst_col

                            if 0 <= src < len(cols) and 0 <= dst < len(cols):
                                src_cards = cols[src].cards
                                if src_cards and cols[dst].cards:
                                    src_suit = src_cards[-1].suit if src_cards else None
                                    dst_suit = cols[dst].cards[-1].suit if cols[dst].cards else None
                                    if src_suit == dst_suit:
                                        same_suit_moves += 1

                            if 0 <= src < len(cols) and prev_cols:
                                prev_col = prev_cols[src] if src < len(prev_cols) else None
                                if prev_col and prev_col.face_down_count > 0:
                                    expose_moves += 1

                            if 0 <= dst < len(cols) and len(cols[dst].cards) == 1:
                                use_empty_moves += 1

                            if 0 <= src < len(cols) and prev_cols:
                                prev_col = prev_cols[src] if src < len(prev_cols) else None
                                if prev_col and prev_col.face_down_count == 0:
                                    pass
                                else:
                                    non_reversible += 1

                        elif move and move.is_deal:
                            total_deals += 1
                            if len(legal) > 1:
                                deal_when_movable += 1

                        for c in state.columns:
                            if c.is_empty:
                                empty_available += 1

                        choices_per_state.append(len(legal))
                        prev_cols = state.columns

                def safe_div(a, b): return a / b if b > 0 else 0.0

                f0 = safe_div(same_suit_moves, total_moves)
                f1 = safe_div(expose_moves, total_moves)
                f2 = 0.0
                f3 = safe_div(use_empty_moves, empty_available)
                f4 = safe_div(deal_when_movable, total_deals)
                f5 = 1.0 - safe_div(non_reversible, total_moves)
                f6 = safe_div(destructive_moves, total_moves)
                import statistics
                if len(choices_per_state) > 1:
                    cv = statistics.stdev(choices_per_state) / max(1, statistics.mean(choices_per_state))
                    f7 = max(0, 1 - cv)
                else:
                    f7 = 0.0

                factors = [
                    {"name": "花色保持", "score": round(f0, 3)},
                    {"name": "翻牌意愿", "score": round(f1, 3)},
                    {"name": "序列构建", "score": round(f2, 3)},
                    {"name": "空列利用", "score": round(f3, 3)},
                    {"name": "发牌时机", "score": round(f4, 3)},
                    {"name": "可逆偏好", "score": round(f5, 3)},
                    {"name": "风险容忍", "score": round(f6, 3)},
                    {"name": "决策一致", "score": round(f7, 3)},
                ]
                return {"ok": True, "strategy": strategy_name, "factors": factors, "total_moves": total_moves}

            self._submit_background(task_id, _compute)
            return jsonify({"ok": True, "task_id": task_id, "message": "因子计算已提交，请轮询 /api/task/{task_id} 获取结果"})

        # 搜索树可视化
        @app.route("/api/search-tree")
        def search_tree():
            from src.strategy.registry import get_strategy
            try:
                strategy = self._get_strategy(
                    request.args.get("strategy", "mcts")
                )
                if hasattr(strategy, "get_search_tree"):
                    tree = strategy.get_search_tree()
                    if tree:
                        return jsonify({"ok": True, "tree": tree})
                return jsonify({"ok": False, "error": "无搜索树数据"})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})

        # 牌局回放
        @app.route("/api/replay")
        def replay():
            games = self._exporter.get_history()
            if not games:
                return jsonify({"ok": False, "error": "无历史牌局"})
            idx = int(request.args.get("index", len(games) - 1))
            if 0 <= idx < len(games):
                return jsonify({"ok": True, "game": games[idx], "total": len(games)})
            return jsonify({"ok": False, "error": "索引越界"})

        # 策略热切换
        @app.route("/api/switch-strategy", methods=["POST"])
        def switch_strategy():
            data = request.get_json(silent=True) or {}
            new_name = data.get("strategy", "mcts")
            try:
                from src.strategy.registry import get_strategy
                get_strategy(new_name)  # 验证存在
                return jsonify({"ok": True, "strategy": new_name})
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)})

        # 遗传算法优化（后台执行）
        @app.route("/api/genetic-optimize", methods=["POST"])
        def genetic_optimize():
            import uuid
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "mcts")
            difficulty = data.get("difficulty", 1)
            generations = min(data.get("generations", 10), 30)
            pop_size = min(data.get("pop_size", 8), 20)
            task_id = f"genetic_{uuid.uuid4().hex[:8]}"

            def _run():
                from src.analysis.genetic import GeneticOptimizer
                param_space = {
                    "iterations": [100, 200, 500],
                    "time_limit": [0.1, 0.2, 0.5],
                    "exploration": [0.8, 1.0, 1.4, 2.0],
                }
                ga = GeneticOptimizer(strategy_name, param_space)
                result = ga.evolve(difficulty=difficulty, pop_size=pop_size, generations=generations, games_per_eval=5)
                return result.to_dict()

            self._submit_background(task_id, _run)
            return jsonify({"ok": True, "task_id": task_id})

        # 模式挖掘
        @app.route("/api/mine-patterns", methods=["POST"])
        def mine_patterns():
            try:
                games = self._exporter.get_history()
                if not games:
                    return jsonify({"ok": False, "error": "无历史数据，请先运行牌局"})
                from src.analysis.pattern import PatternMiner
                miner = PatternMiner()
                report = miner.mine(games)
                return jsonify({"ok": True, **report.to_dict()})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})

        # 策略对抗锦标赛（后台执行）
        @app.route("/api/tournament", methods=["POST"])
        def tournament():
            import uuid
            data = request.get_json(silent=True) or {}
            strategy_names = data.get("strategies", ["greedy", "mcts"])
            difficulty = data.get("difficulty", 1)
            num_games = min(data.get("num_games", 10), 30)
            task_id = f"tournament_{uuid.uuid4().hex[:8]}"

            def _run():
                from src.analysis.tournament import Tournament
                t = Tournament()
                result = t.run(strategy_names, difficulty=difficulty, seeds=range(1, num_games + 1))
                return result.to_dict()

            self._submit_background(task_id, _run)
            return jsonify({"ok": True, "task_id": task_id})

        # 神经网络训练
        @app.route("/api/neural-train", methods=["POST"])
        def neural_train():
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "greedy")
            difficulty = data.get("difficulty", 1)
            num_games = min(data.get("num_games", 50), 200)
            try:
                from src.strategy.neural import NeuralTrainer
                trainer = NeuralTrainer()
                features, labels = trainer.collect_data(strategy_name, difficulty, num_games, sample_rate=0.1)
                losses = trainer.train(features, labels, epochs=30, lr=0.001)
                model_path = str(get_models_dir() / "neural_model.npz")
                Path(model_path).parent.mkdir(parents=True, exist_ok=True)
                trainer.save_model(model_path)
                return jsonify({
                    "ok": True, "samples": len(features),
                    "final_loss": round(losses[-1], 6) if losses else 0,
                    "model_path": model_path,
                })
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})

        # 系统性能监控
        @app.route("/api/system")
        def system_status():
            import psutil
            data = {
                "cpu_percent": psutil.cpu_percent(interval=0),
                "cpu_count": psutil.cpu_count(),
                "mem_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
                "mem_used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
                "mem_percent": psutil.virtual_memory().percent,
            }
            # GPU（NVIDIA）
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    data["gpu_name"] = g.name
                    data["gpu_load"] = round(g.load * 100, 1)
                    data["gpu_mem_used_mb"] = round(g.memoryUsed, 0)
                    data["gpu_mem_total_mb"] = round(g.memoryTotal, 0)
                    data["gpu_temp"] = g.temperature
                else:
                    data["gpu_name"] = None
            except Exception:
                data["gpu_name"] = None
            return jsonify(data)

        # 批量模拟（多进程并行）
        @app.route("/api/run", methods=["POST"])
        def run_batch():
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "greedy")
            difficulty = data.get("difficulty", 1)
            count = min(data.get("count", 10), 500)

            from src.analysis.batch import run_batch_parallel

            results = run_batch_parallel(
                strategy_name=strategy_name,
                difficulty=difficulty,
                count=count,
            )

            wins = sum(1 for r in results if r["result"] == "WIN")
            return jsonify({
                "ok": True,
                "total": len(results),
                "wins": wins,
                "win_rate": f"{wins / len(results) * 100:.1f}%",
                "results": results,
            })

        # 运行实验
        @app.route("/api/run-experiment", methods=["POST"])
        def run_experiment():
            data = request.get_json(silent=True) or {}
            strategies = {}
            for s in data.get("strategies", [{"name": "mcts"}]):
                strategies[s["name"]] = self._get_strategy(s["name"])

            difficulty = data.get("difficulty", 2)
            count = data.get("count", 50)

            def _run():
                result = self._experiment_runner.run(
                    strategies=strategies,
                    difficulty=difficulty,
                    seeds=list(range(1, count + 1)),
                    output_dir=data.get("output_dir"),
                )
                self._broadcast({"type": "experiment_done", "result": result})

            threading.Thread(target=_run, daemon=True).start()
            return jsonify({"ok": True, "message": f"实验已启动: {count} 局"})

        # ── 迭代引擎 API ──

        # 运行一次策略迭代
        @app.route("/api/iterate", methods=["POST"])
        def run_iteration():
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "mcts")
            params = data.get("params", {})
            difficulty = data.get("difficulty", 1)
            num_games = min(data.get("num_games", 30), 100)
            try:
                from src.iteration.engine import IterationEngine, StrategyManifest
                engine = IterationEngine(output_dir=str(get_iterations_dir()))
                manifest = StrategyManifest(
                    name=strategy_name,
                    display_name=strategy_name,
                    params=params,
                    source="api",
                )
                record = engine.iterate(
                    manifest=manifest,
                    difficulty=difficulty,
                    num_games=num_games,
                )
                return jsonify({"ok": True, **record.to_dict()})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        # 获取迭代历史
        @app.route("/api/iterations")
        def get_iterations():
            try:
                from src.iteration.engine import IterationEngine
                engine = IterationEngine(output_dir=str(get_iterations_dir()))
                records = engine.load_history()
                return jsonify({
                    "ok": True,
                    "count": len(records),
                    "records": [r.to_dict() for r in records],
                    "summary": engine.evolution_summary(),
                })
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})

        # 导出策略清单
        @app.route("/api/manifest/export", methods=["POST"])
        def export_manifest():
            data = request.get_json(silent=True) or {}
            try:
                from src.iteration.engine import StrategyManifest
                manifest = StrategyManifest(
                    name=data.get("strategy", "mcts"),
                    display_name=data.get("display_name", ""),
                    params=data.get("params", {}),
                    source="manual",
                    notes=data.get("notes", ""),
                )
                out_dir = get_iterations_dir()
                path = manifest.save(out_dir / f"manifest_{manifest.name}_v{manifest.version}.json")
                return jsonify({"ok": True, "path": str(path), **manifest.to_dict()})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        # 加载策略清单
        @app.route("/api/manifest/load", methods=["POST"])
        def load_manifest():
            data = request.get_json(silent=True) or {}
            path = data.get("path", "")
            try:
                from src.iteration.engine import StrategyManifest
                from src.strategy.registry import register_from_config
                manifest = StrategyManifest.load(path)
                register_from_config(
                    name=f"custom_{manifest.name}",
                    base_strategy=manifest.name,
                    params=manifest.params,
                    display_name=manifest.display_name,
                )
                return jsonify({"ok": True, **manifest.to_dict()})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        # 列出已保存的策略清单
        @app.route("/api/manifests")
        def list_manifests():
            try:
                from src.iteration.engine import IterationEngine
                engine = IterationEngine(output_dir=str(get_iterations_dir()))
                manifests = engine.load_manifests()
                return jsonify({
                    "ok": True,
                    "count": len(manifests),
                    "manifests": [m.to_dict() for m in manifests],
                })
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)})

        # 策略弱点检测 + 参数建议
        @app.route("/api/weakness-suggest", methods=["POST"])
        def weakness_suggest():
            data = request.get_json(silent=True) or {}
            strategy_name = data.get("strategy", "greedy")
            factors = data.get("factors", {})
            try:
                from src.analysis.weakness import detect_weaknesses, suggest_params
                report = detect_weaknesses(strategy_name, factors)
                suggestions = suggest_params(strategy_name, report)
                return jsonify({
                    "ok": True,
                    "weaknesses": report.to_dict(),
                    "suggestions": suggestions,
                })
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

    def _get_strategy(self, name: str) -> Strategy:
        """获取策略实例（通过注册中心）"""
        from src.strategy.registry import get_strategy
        return get_strategy(name)

    def _on_auto_step(self, step_record) -> None:
        """自动运行时的步进回调"""
        self._current_state = step_record.state
        self._step_log.append(step_record.to_dict())
        # 记录到导出器
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
        # 策略统计数据
        strategy_stats = {}
        if hasattr(self, '_current_strategy'):
            s = self._current_strategy
            if hasattr(s, 'last_iterations'):
                strategy_stats = {
                    "iterations": s.last_iterations,
                    "tree_size": s.last_tree_size,
                    "memory_hit_rate": round(s.memory_hit_rate, 3),
                }
        self._broadcast({
            "type": "auto_step",
            "step": step_record.to_dict(),
            "state": step_record.state.to_dict(),
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
        # 策略统计数据
        if self._running and self._env:
            strategy_name = getattr(self, '_current_strategy_name', 'mcts')
            try:
                strategy = self._get_strategy(strategy_name)
                if hasattr(strategy, 'last_iterations'):
                    data["strategy_stats"] = {
                        "iterations": strategy.last_iterations,
                        "tree_size": strategy.last_tree_size,
                        "memory_hit_rate": round(strategy.memory_hit_rate, 3),
                    }
            except Exception:
                pass
        return data

    def _broadcast(self, data: dict) -> None:
        """SSE 广播"""
        for q in self._sse_queues:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass

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
