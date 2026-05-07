"""
前后端 API 匹配测试 — 覆盖已知不匹配问题
"""

import pytest
import re
from src.ui.server import SpideretteUI


@pytest.fixture
def client():
    ui = SpideretteUI()
    ui.app.config["TESTING"] = True
    with ui.app.test_client() as client:
        yield client


class TestCompareAPISync:
    def test_compare_returns_rankings_not_task_id(self, client):
        resp = client.post("/api/compare", json={
            "strategies": ["greedy", "random"],
            "difficulty": 1,
            "num_games": 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "rankings" in data, f"compare 应返回 rankings，实际: {list(data.keys())}"
        assert "task_id" not in data

    def test_compare_rankings_structure(self, client):
        resp = client.post("/api/compare", json={
            "strategies": ["greedy", "random"],
            "difficulty": 1,
            "num_games": 2,
        })
        data = resp.get_json()
        rankings = data.get("rankings", {})
        for key in ["best_win_rate", "best_efficiency", "best_avg_moves"]:
            assert key in rankings, f"rankings 缺少 {key}"


class TestTournamentAPISync:
    def test_tournament_returns_standings_not_task_id(self, client):
        resp = client.post("/api/tournament", json={
            "strategies": ["greedy", "random"],
            "difficulty": 1,
            "num_games": 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "standings" in data
        assert "task_id" not in data

    def test_tournament_standings_structure(self, client):
        resp = client.post("/api/tournament", json={
            "strategies": ["greedy", "random"],
            "difficulty": 1,
            "num_games": 2,
        })
        data = resp.get_json()
        standings = data.get("standings", {})
        assert len(standings) >= 2
        for name, stats in standings.items():
            assert "win_rate" in stats
            assert "score" in stats


class TestGeneticOptimizeAPISync:
    def test_genetic_returns_best_not_task_id(self, client):
        resp = client.post("/api/genetic-optimize", json={
            "strategy": "greedy",
            "difficulty": 1,
            "generations": 1,
            "pop_size": 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "best" in data
        assert "task_id" not in data

    def test_genetic_best_structure(self, client):
        resp = client.post("/api/genetic-optimize", json={
            "strategy": "greedy",
            "difficulty": 1,
            "generations": 1,
            "pop_size": 2,
        })
        data = resp.get_json()
        best = data.get("best", {})
        for key in ["params", "fitness", "win_rate"]:
            assert key in best, f"best 缺少 {key}"


class TestCalcFactorsAPISync:
    def test_calc_factors_returns_factors_not_task_id(self, client):
        resp = client.post("/api/calc-factors", json={
            "strategy": "greedy",
            "difficulty": 1,
            "num_games": 2,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "factors" in data
        assert "task_id" not in data

    def test_calc_factors_structure(self, client):
        resp = client.post("/api/calc-factors", json={
            "strategy": "greedy",
            "difficulty": 1,
            "num_games": 2,
        })
        data = resp.get_json()
        factors = data.get("factors", [])
        assert len(factors) > 0
        for f in factors:
            assert "name" in f
            assert "score" in f


class TestSSEFieldName:
    def test_sse_broadcast_field_matches_frontend(self, client):
        import inspect
        source = inspect.getsource(SpideretteUI._broadcast_full_state)
        assert "_sse_seq" in source, (
            "后端 _broadcast_full_state 应使用 _sse_seq 字段名（前端读 d._sse_seq）"
        )


class TestFrontendAPICompleteness:
    def test_all_frontend_endpoints_registered(self, client):
        resp = client.get("/")
        html = resp.data.decode("utf-8")
        pattern = r"api\('([^']+)'"
        frontend_endpoints = set(re.findall(pattern, html))
        routes = set()
        for rule in client.application.url_map.iter_rules():
            if rule.endpoint != "static":
                path = rule.rule.rstrip("/")
                routes.add(path)
        missing = []
        for ep in frontend_endpoints:
            base_ep = ep.split("?")[0]
            api_path = f"/api/{base_ep}"
            if api_path not in routes:
                missing.append(api_path)
        assert not missing, f"前端调用了但后端未注册的端点: {missing}"


class TestAllEndpointsReturnExpectedFields:
    def test_weakness_returns_expected_fields(self, client):
        resp = client.post("/api/weakness", json={"strategy": "greedy", "factors": {}})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "weaknesses" in data

    def test_mine_patterns_returns_expected_fields(self, client):
        resp = client.post("/api/mine-patterns", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        if data.get("ok"):
            assert "patterns" in data

    def test_neural_train_returns_expected_fields(self, client):
        resp = client.post("/api/neural-train", json={"strategy": "greedy", "num_games": 5})
        assert resp.status_code == 200
        data = resp.get_json()
        if data.get("ok"):
            assert "samples" in data
            assert "final_loss" in data

    def test_run_returns_expected_fields(self, client):
        resp = client.post("/api/run", json={"strategy": "greedy", "difficulty": 1, "count": 2})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "total" in data
        assert "wins" in data
        assert "win_rate" in data

    def test_project_meta_returns_expected_fields(self, client):
        resp = client.get("/api/project-meta")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "name" in data
        assert "version" in data

    def test_system_returns_expected_fields(self, client):
        resp = client.get("/api/system")
        assert resp.status_code == 200
        data = resp.get_json()
        for field in ["cpu_percent", "mem_percent", "mem_used_gb", "mem_total_gb", "cpu_count"]:
            assert field in data, f"system 缺少字段 {field}"

    def test_search_tree_returns_expected_fields(self, client):
        # search-tree requires a strategy with get_search_tree (e.g. mcts)
        # and a game in progress; be lenient as tree data is strategy-dependent
        client.post("/api/new-game", json={"difficulty": 1})
        resp = client.get("/api/search-tree?strategy=mcts")
        assert resp.status_code == 200
        data = resp.get_json()
        # Tree may not be available without prior MCTS steps, but endpoint should respond
        assert "ok" in data
