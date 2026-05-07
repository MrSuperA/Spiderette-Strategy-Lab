"""
iteration routes - extracted from server.py
"""
from __future__ import annotations
from flask import jsonify, request
from src.utils.logging import get_logger
from src.utils.config import get_config
from src.utils.paths import get_iterations_dir

_logger = get_logger(__name__)


def register_iteration_routes(app, ui):
    """Register iteration routes"""
    cfg = get_config()

    @app.route("/api/iterate", methods=["POST"])
    def run_iteration():
        data = request.get_json(silent=True) or {}
        strategy_name = data.get("strategy", "mcts")
        params = data.get("params", {})
        difficulty = data.get("difficulty", cfg.get("analysis", "difficulty", 1))
        num_games = min(data.get("num_games", cfg.get("analysis", "num_games", 30)), cfg.get("analysis", "max_games", 100))
        try:
            from src.core.manifest import StrategyManifest
            from src.iteration.engine import IterationEngine
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
            from src.core.manifest import StrategyManifest
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
            from src.core.manifest import StrategyManifest
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

