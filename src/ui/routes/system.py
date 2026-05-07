"""
system routes - extracted from server.py
"""
from __future__ import annotations
import json
import os
import queue
import tempfile
from flask import Response, jsonify, request, send_from_directory
from pathlib import Path
from src.utils.logging import get_logger

STATIC_DIR = Path(__file__).parent.parent / "static"

_logger = get_logger(__name__)


def register_system_routes(app, ui):
    """Register system routes"""

    @app.route("/api/version")
    def version():
        from src import __version__
        return jsonify({"version": __version__})

    @app.route("/api/project-meta")
    def project_meta():
        """返回 pyproject.toml 中的完整项目元数据"""
        from tools.sync_docs import _read_project_meta, _read_version
        meta = _read_project_meta()
        meta["version"] = _read_version()
        return jsonify(meta)

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
        ui._sse_queues.append(q)

        def generate():
            try:
                while True:
                    try:
                        data = q.get(timeout=1.0)
                        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
            finally:
                if q in ui._sse_queues:
                    ui._sse_queues.remove(q)

        return Response(generate(), mimetype="text/event-stream")

    # 状态查询
    @app.route("/api/status")
    def status():
        return jsonify(ui._get_status())

    # 开始新牌局
    @app.route("/api/strategies")
    def strategies():
        from src.strategy.registry import list_strategies
        return jsonify({"strategies": list_strategies()})

    # 多策略对比（后台执行）
    @app.route("/api/task/<task_id>")
    def get_task_status(task_id):
        status = ui._get_task_status(task_id)
        return jsonify({"ok": True, **status})

    # 策略量化因子计算（后台执行，避免阻塞 Waitress 线程）
    @app.route("/api/search-tree")
    def search_tree():
        from src.strategy.registry import get_strategy
        try:
            strategy = ui._get_strategy(
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

    # ── 自定义策略导入 ──
    @app.route("/api/import-strategy", methods=["POST"])
    def import_strategy():
        """从 manifest JSON 文件导入自定义策略"""
        from src.strategy.registry import register_from_manifest, list_strategies
        from src.core.manifest import StrategyManifest
        try:
            data = request.get_json(silent=True) or {}
            manifest_data = data.get("manifest")
            if not manifest_data:
                return jsonify({"ok": False, "error": "缺少 manifest 数据"}), 400

            # 验证 manifest 格式
            manifest = StrategyManifest.from_dict(manifest_data)

            # 校验 base_strategy：必须明确指定，不能与 name 相同
            if not manifest.base_strategy:
                return jsonify({"ok": False, "error": "manifest 缺少 base_strategy 字段，请指定基础策略（如 mcts、greedy）"}), 400
            if manifest.base_strategy == manifest.name:
                return jsonify({"ok": False, "error": f"base_strategy 不能与 name 相同（都是 {manifest.name}），请指定一个已存在的内置策略"}), 400

            # 写入临时文件再加载（复用现有 register_from_manifest）
            tmp_path = os.path.join(tempfile.gettempdir(), f"custom_strategy_{manifest.name}.json")
            manifest.save(tmp_path)

            # 注册到策略中心
            register_from_manifest(tmp_path)

            _logger.info("自定义策略已导入: %s (%s)", manifest.name, manifest.display_name)
            return jsonify({
                "ok": True,
                "strategy": manifest.name,
                "display_name": manifest.display_name,
                "strategies": list_strategies(),
            })
        except Exception as e:
            _logger.error("策略导入失败: %s", e, exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500

    # 批量模拟（多进程并行）

