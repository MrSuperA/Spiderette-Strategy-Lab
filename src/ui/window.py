"""
Native window wrapper - pywebview + WebView2 + Waitress production server
"""

from __future__ import annotations

import sys
import threading
import time
import traceback

from src.ui.server import SpideretteUI
from src.utils.logging import get_logger
from src.utils.config import get_config

_logger = get_logger(__name__)


def run_window(
    host: str | None = None,
    port: int | None = None,
    title: str = "Spiderette Strategy Lab",
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Launch standalone native window — window opens immediately, server starts in parallel"""
    import webview

    cfg = get_config()
    wcfg = cfg.section("window")
    host = host or cfg.get("server", "host", "127.0.0.1")
    port = port or wcfg.get("server", "port", 5679)
    width = width or wcfg.get("width", 1280)
    height = height or wcfg.get("height", 800)
    min_w = wcfg.get("min_width", 960)
    min_h = wcfg.get("min_height", 600)
    threads = wcfg.get("threads", 16)
    channel_timeout = wcfg.get("channel_timeout", 30)
    recv_bytes = wcfg.get("recv_bytes", 65536)
    send_bytes = wcfg.get("send_bytes", 65536)
    startup_timeout = wcfg.get("startup_timeout", 15)

    ui = SpideretteUI(host=host, port=port)
    url = f"http://{host}:{port}"

    # Waitress production server (multi-threaded, connection pool)
    def _run_server():
        try:
            from waitress import serve
            serve(
                ui.app,
                host=host,
                port=port,
                threads=threads,
                channel_timeout=channel_timeout,
                recv_bytes=recv_bytes,
                send_bytes=send_bytes,
                expose_tracebacks=False,
            )
        except ImportError:
            _logger.warning("waitress not installed, falling back to Flask dev server (limited performance)")
            ui.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        except OSError as e:
            _logger.error("Server startup failed: %s", e)

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Open window immediately with loading page — no waiting
    _logger.info("Opening window immediately (server starting in background)")

    loading_html = """<!DOCTYPE html><html><head><meta charset="utf-8">
    <style>body{margin:0;display:flex;align-items:center;justify-content:center;
    height:100vh;background:#06080d;color:#7e8da0;font-family:system-ui,sans-serif}
    .ld{text-align:center}.ld h2{font-size:16px;color:#4facfe;margin-bottom:12px}
    .spinner{width:24px;height:24px;border:2px solid rgba(79,172,254,.15);
    border-top-color:#4facfe;border-radius:50%;animation:spin .8s linear infinite;
    margin:0 auto 12px}@keyframes spin{to{transform:rotate(360deg)}}</style></head>
    <body><div class="ld"><div class="spinner"></div><h2>♠ Spiderette Strategy Lab</h2>
    <p>正在启动服务...</p></div></body></html>"""

    window = webview.create_window(
        title=title,
        html=loading_html,
        width=width,
        height=height,
        min_size=(min_w, min_h),
        text_select=True,
    )

    def on_closed():
        _logger.info("Window closed")

    window.events.closed += on_closed

    # Start a thread to switch URL once server is ready
    def _switch_when_ready():
        if _wait_for_server(url, timeout=startup_timeout):
            _logger.info("Server ready, switching to app")
            try:
                window.load_url(url)
            except Exception:
                pass
        else:
            _logger.error("Server not ready after %ds", startup_timeout)
            try:
                window.load_html("""<!DOCTYPE html><html><head><meta charset="utf-8">
                <style>body{margin:0;display:flex;align-items:center;justify-content:center;
                height:100vh;background:#06080d;color:#f87171;font-family:system-ui,sans-serif}
                .ld{text-align:center}.ld h2{font-size:16px;margin-bottom:8px}
                p{color:#7e8da0;font-size:13px}</style></head>
                <body><div class="ld"><h2>⚠ 启动失败</h2>
                <p>服务未能在 %ds 内就绪，请检查端口占用后重试。</p></div></body></html>""" % startup_timeout)
            except Exception:
                pass

    switcher = threading.Thread(target=_switch_when_ready, daemon=True)
    switcher.start()

    try:
        webview.start(gui="edgechromium", debug=False)
    except Exception:
        try:
            webview.start(debug=False)
        except Exception as e:
            _logger.error("Window startup failed: %s", e)
            traceback.print_exc()
            input("Press Enter to exit...")

    _logger.info("Exited")


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """Wait for server ready"""
    import urllib.request
    import urllib.error

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False
