"""
Web UI API 集成测试 — 使用 Flask test client
覆盖：状态查询、新游戏、策略列表、版本号、批量模拟
"""

import pytest
import json
from src.ui.server import SpideretteUI


@pytest.fixture
def client():
    """创建 Flask 测试客户端"""
    ui = SpideretteUI()
    ui.app.config["TESTING"] = True
    with ui.app.test_client() as client:
        yield client


class TestStatusAPI:
    """状态查询"""

    def test_status_returns_json(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "running" in data
        assert "has_env" in data

    def test_version_returns_json(self, client):
        resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "version" in data


class TestGameAPI:
    """游戏控制"""

    def test_new_game(self, client):
        resp = client.post("/api/new-game", json={"seed": 42, "difficulty": 1, "strategy": "greedy"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "state" in data

    def test_step_without_game(self, client):
        resp = client.post("/api/step", json={"strategy": "greedy"})
        assert resp.status_code == 400

    def test_step_after_new_game(self, client):
        client.post("/api/new-game", json={"seed": 42, "difficulty": 1})
        resp = client.post("/api/step", json={"strategy": "greedy"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "state" in data

    def test_stop(self, client):
        resp = client.post("/api/stop")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


class TestStrategiesAPI:
    """策略列表"""

    def test_strategies(self, client):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "strategies" in data
        assert len(data["strategies"]) >= 5

    def test_strategies_have_names(self, client):
        data = client.get("/api/strategies").get_json()
        names = {s["name"] for s in data["strategies"]}
        assert "greedy" in names
        assert "mcts" in names


class TestCompareAPI:
    """策略对比（异步）"""

    def test_compare_returns_task_id(self, client):
        resp = client.post("/api/compare", json={
            "strategies": ["greedy", "random"],
            "difficulty": 1,
            "num_games": 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "task_id" in data

    def test_task_status_endpoint(self, client):
        """任务状态查询端点可用"""
        resp = client.get("/api/task/nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["status"] == "unknown"


class TestSystemAPI:
    """系统监控"""

    def test_system_status(self, client):
        resp = client.get("/api/system")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "cpu_percent" in data
        assert "mem_percent" in data


class TestExportAPI:
    """导出"""

    def test_export_history_empty(self, client):
        resp = client.get("/api/export/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["games"] == []


class TestIndexPage:
    """首页"""

    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Spiderette" in resp.data or b"html" in resp.data.lower()
