"""
原生窗口封装 — pywebview + WebView2 + Waitress 生产级服务器
"""

from __future__ import annotations

import sys
import threading
import time
import traceback

from src.ui.server import SpideretteUI


def run_window(
    host: str = "127.0.0.1",
    port: int = 5679,
    title: str = "Spiderette Strategy Lab",
    width: int = 1280,
    height: int = 800,
) -> None:
    """启动独立原生窗口"""
    import webview

    ui = SpideretteUI(host=host, port=port)
    url = f"http://{host}:{port}"

    # Waitress 生产级服务器（多线程，连接池，稳定）
    def _run_server():
        try:
            from waitress import serve
            serve(
                ui.app,
                host=host,
                port=port,
                threads=16,          # 16 工作线程（并发处理）
                channel_timeout=30,  # 连接超时 30 秒
                recv_bytes=65536,    # 接收缓冲区 64KB
                send_bytes=65536,    # 发送缓冲区 64KB
                expose_tracebacks=False,
            )
        except ImportError:
            # waitress 不可用时回退到 Flask 开发服务器
            print("[警告] waitress 未安装，使用 Flask 开发服务器（性能受限）", flush=True)
            ui.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        except OSError as e:
            print(f"[错误] 服务器启动失败: {e}", flush=True)

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # 等待服务器就绪
    print(f"[Spiderette] 等待服务就绪...", flush=True)
    if not _wait_for_server(url, timeout=15):
        print(f"[错误] 服务未就绪: {url}", flush=True)
        input("按回车键退出...")
        return

    print(f"[Spiderette] 服务就绪，打开窗口...", flush=True)

    # 创建窗口
    window = webview.create_window(
        title=title,
        url=url,
        width=width,
        height=height,
        min_size=(960, 600),
        text_select=True,
    )

    def on_closed():
        print("[Spiderette] 窗口已关闭", flush=True)

    window.events.closed += on_closed

    try:
        webview.start(gui="edgechromium", debug=False)
    except Exception:
        try:
            webview.start(debug=False)
        except Exception as e:
            print(f"[错误] 窗口启动失败: {e}", flush=True)
            traceback.print_exc()
            input("按回车键退出...")

    print("[Spiderette] 已退出", flush=True)


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """等待服务器就绪"""
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
