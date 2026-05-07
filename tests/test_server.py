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

    BUILTINS = {"mcts", "mcts_fast", "mcts_deep", "greedy", "random", "neural", "is_mcts", "puct"}

    def test_strategies(self, client):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "strategies" in data
        assert len(data["strategies"]) >= 8

    def test_strategies_have_names(self, client):
        data = client.get("/api/strategies").get_json()
        names = {s["name"] for s in data["strategies"]}
        assert "greedy" in names
        assert "mcts" in names

    def test_all_builtins_present(self, client):
        """所有内置策略必须出现在 API 返回中"""
        data = client.get("/api/strategies").get_json()
        names = {s["name"] for s in data["strategies"]}
        missing = self.BUILTINS - names
        assert not missing, f"API 缺少内置策略: {missing}"

    def test_strategies_match_registry(self, client):
        """API 返回的策略列表必须与 registry 完全一致"""
        from src.strategy.registry import list_strategies
        api_names = {s["name"] for s in client.get("/api/strategies").get_json()["strategies"]}
        reg_names = {s["name"] for s in list_strategies()}
        assert api_names == reg_names, f"API 与 registry 不一致: 多余={api_names-reg_names}, 缺少={reg_names-api_names}"


class TestImportStrategyAPI:
    """策略导入"""

    def test_import_valid_manifest(self, client):
        manifest = {
            "name": "test_import_valid",
            "display_name": "测试导入",
            "base_strategy": "mcts",
            "params": {"iterations": 100},
            "version": "1.0.0",
            "notes": "测试",
        }
        resp = client.post("/api/import-strategy", json={"manifest": manifest})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["strategy"] == "test_import_valid"
        # 确认出现在策略列表中
        names = {s["name"] for s in data["strategies"]}
        assert "test_import_valid" in names

    def test_import_missing_manifest(self, client):
        resp = client.post("/api/import-strategy", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False

    def test_import_missing_base_strategy(self, client):
        resp = client.post("/api/import-strategy", json={"manifest": {"name": "x", "display_name": "X"}})
        assert resp.status_code == 400
        assert "base_strategy" in resp.get_json()["error"]

    def test_import_self_reference(self, client):
        resp = client.post("/api/import-strategy", json={"manifest": {"name": "foo", "display_name": "Foo", "base_strategy": "foo"}})
        assert resp.status_code == 400
        assert "相同" in resp.get_json()["error"]

    def test_imported_strategy_usable(self, client):
        """导入的策略可以通过 step 使用"""
        manifest = {
            "name": "test_import_usable",
            "display_name": "可使用导入",
            "base_strategy": "greedy",
            "params": {},
            "version": "1.0.0",
        }
        client.post("/api/import-strategy", json={"manifest": manifest})
        # 创建游戏并用导入的策略走一步
        client.post("/api/new-game", json={"seed": 1, "difficulty": 1})
        resp = client.post("/api/step", json={"strategy": "test_import_usable"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True


class TestFrontendBackendConsistency:
    """前端 HTML 与后端 API 一致性"""

    def test_frontend_select_loads_from_api(self, client):
        """前端策略 select 必须是动态加载（空 select），不能硬编码选项"""
        resp = client.get("/")
        html = resp.data.decode("utf-8")
        # 硬编码的 option 标签不应该存在于 select#selStrat 中
        assert '<option value="greedy">贪心</option>' not in html,             "前端策略下拉框仍硬编码了选项，应改为动态加载"
        # 应该有 loadStrategies 函数
        assert "loadStrategies" in html, "前端缺少 loadStrategies 函数"

    def test_frontend_import_button_exists(self, client):
        """前端应有导入按钮"""
        resp = client.get("/")
        html = resp.data.decode("utf-8")
        assert "showImportStrategy" in html, "前端缺少导入策略按钮"

    def test_frontend_import_endpoint_called(self, client):
        """前端应调用 /api/import-strategy"""
        resp = client.get("/")
        html = resp.data.decode("utf-8")
        assert "import-strategy" in html, "前端未调用 /api/import-strategy 端点"


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
