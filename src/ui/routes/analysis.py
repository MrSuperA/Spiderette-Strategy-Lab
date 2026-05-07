"""
analysis routes - extracted from server.py
"""
from __future__ import annotations
import threading
from flask import jsonify, request
from src.envs.simulator import SimulatorEnv
from src.core.session import GameSession
from src.utils.logging import get_logger
from src.utils.paths import get_models_dir
from pathlib import Path

_logger = get_logger(__name__)


def register_analysis_routes(app, ui):
    """Register analysis routes"""

    @app.route("/api/compare", methods=["POST"])
    def compare_strategies_endpoint():
        data = request.get_json(silent=True) or {}
        strategy_names = data.get("strategies", ["greedy", "mcts"])
        difficulty = data.get("difficulty", 1)
        num_games = min(data.get("num_games", 10), 50)
        try:
            from src.analysis.compare import ParallelStrategyRunner
            runner = ParallelStrategyRunner()
            report = runner.compare(
                strategy_names=strategy_names,
                difficulty=difficulty,
                seeds=list(range(1, num_games + 1)),
                parallel=False,
            )
            report_dict = report.to_dict()
            # Frontend reads d.rankings.best_win_rate directly, flatten nested structure
            inner = report_dict.get("rankings", report_dict)
            return jsonify({"ok": True, "rankings": inner})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

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
    @app.route("/api/calc-factors", methods=["POST"])
    def calc_factors():
        data = request.get_json(silent=True) or {}
        strategy_name = data.get("strategy", "greedy")
        difficulty = data.get("difficulty", 1)
        num_games = min(data.get("num_games", 10), 50)
        try:
            strategy = ui._get_strategy(strategy_name)
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

            factors_list = [
                {"name": "花色保持", "score": round(f0, 3)},
                {"name": "翻牌意愿", "score": round(f1, 3)},
                {"name": "序列构建", "score": round(f2, 3)},
                {"name": "空列利用", "score": round(f3, 3)},
                {"name": "发牌时机", "score": round(f4, 3)},
                {"name": "可逆偏好", "score": round(f5, 3)},
                {"name": "风险容忍", "score": round(f6, 3)},
                {"name": "决策一致", "score": round(f7, 3)},
            ]
            return jsonify({"ok": True, "factors": factors_list})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # 搜索树可视化
    @app.route("/api/genetic-optimize", methods=["POST"])
    def genetic_optimize():
        data = request.get_json(silent=True) or {}
        strategy_name = data.get("strategy", "mcts")
        difficulty = data.get("difficulty", 1)
        generations = min(data.get("generations", 10), 30)
        pop_size = min(data.get("pop_size", 8), 20)
        try:
            from src.analysis.genetic import GeneticOptimizer
            param_space = {
                "iterations": [100, 200, 500],
                "time_limit": [0.1, 0.2, 0.5],
                "exploration": [0.8, 1.0, 1.4, 2.0],
            }
            ga = GeneticOptimizer(strategy_name, param_space)
            result = ga.evolve(difficulty=difficulty, pop_size=pop_size, generations=generations, games_per_eval=5)
            result_dict = result.to_dict()
            # Frontend reads d.best.params directly, flatten nested best
            best_inner = result_dict.get("best", result_dict)
            return jsonify({"ok": True, "best": best_inner})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # 模式挖掘
    @app.route("/api/mine-patterns", methods=["POST"])
    def mine_patterns():
        try:
            games = ui._exporter.get_history()
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
        data = request.get_json(silent=True) or {}
        strategy_names = data.get("strategies", ["greedy", "mcts"])
        difficulty = data.get("difficulty", 1)
        num_games = min(data.get("num_games", 10), 30)
        try:
            from src.analysis.tournament import Tournament
            t = Tournament()
            result = t.run(strategy_names, difficulty=difficulty, seeds=range(1, num_games + 1))
            result_dict = result.to_dict()
            # Frontend expects standings as {strategy_name: {win_rate, score, ...}}
            # but API returns {standings: [...], matches: [...], ...}
            # Flatten: build strategy->stats mapping from stats
            stats = result_dict.get("stats", {})
            flat_standings = {}
            for name in strategy_names:
                s = stats.get(name, {})
                flat_standings[name] = {
                    "win_rate": s.get("win_rate", 0),
                    "score": s.get("score", 0),
                    "total_games": s.get("total_games", 0),
                    "wins": s.get("wins", 0),
                }
            return jsonify({"ok": True, "standings": flat_standings})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

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
            strategies[s["name"]] = ui._get_strategy(s["name"])

        difficulty = data.get("difficulty", 2)
        count = data.get("count", 50)

        def _run():
            result = ui._experiment_runner.run(
                strategies=strategies,
                difficulty=difficulty,
                seeds=list(range(1, count + 1)),
                output_dir=data.get("output_dir"),
            )
            ui._broadcast({"type": "experiment_done", "result": result})

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"ok": True, "message": f"实验已启动: {count} 局"})

    # ── 迭代引擎 API ──

    # 运行一次策略迭代
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


