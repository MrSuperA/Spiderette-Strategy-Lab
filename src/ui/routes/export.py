"""
export routes - extracted from server.py
"""
from __future__ import annotations
from flask import jsonify, request
from src.utils.logging import get_logger
from src.utils.paths import get_experiments_dir

_logger = get_logger(__name__)


def register_export_routes(app, ui):
    """Register export routes"""

    @app.route("/api/export", methods=["POST"])
    def export_game():
        data = request.get_json(silent=True) or {}
        fmt = data.get("format", "json")
        try:
            out_dir = get_experiments_dir()
            if fmt == "json":
                path = ui._exporter.export_json(out_dir)
            elif fmt == "csv":
                path = ui._exporter.export_csv(out_dir)
            else:
                path = ui._exporter.export_txt(out_dir)
            return jsonify({"ok": True, "path": str(path), "format": fmt})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/export/history")
    def export_history():
        return jsonify({"ok": True, "games": ui._exporter.get_history()})

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
                strategy = ui._get_strategy(strat_name)
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


