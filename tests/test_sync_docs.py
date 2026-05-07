"""sync_docs.py unit tests"""

from __future__ import annotations
import json, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import sync_docs as sd


class TestFileHash:
    def test_sha256_deterministic(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("print(1)\n", encoding="utf-8")
        h1 = sd._file_sha256(f)
        h2 = sd._file_sha256(f)
        assert h1 == h2
        assert len(h1) == 16

    def test_sha256_differs_on_change(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("print(1)\n", encoding="utf-8")
        h1 = sd._file_sha256(f)
        f.write_text("print(2)\n", encoding="utf-8")
        h2 = sd._file_sha256(f)
        assert h1 != h2


class TestASTSymbols:
    def test_extract(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo(): pass\ndef bar(): pass\nclass MyClass: pass\n", encoding="utf-8")
        result = sd._extract_ast_symbols(f)
        assert "foo" in result["functions"]
        assert "bar" in result["functions"]
        assert "MyClass" in result["classes"]

    def test_syntax_error_returns_empty(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def foo(:\n", encoding="utf-8")
        result = sd._extract_ast_symbols(f)
        assert result["functions"] == []
        assert result["classes"] == []


class TestDetectChanges:
    def _meta(self, modules=None, strategies=None, endpoints=None, test_count=0, lines=0):
        return {
            "modules": [{"path": p} for p in (modules or [])],
            "strategies": [{"name": n} for n in (strategies or [])],
            "endpoints": [{"path": p} for p in (endpoints or [])],
            "test_count": test_count,
            "stats": {"total_lines": lines},
        }

    def test_no_changes(self):
        old = self._meta(["a.py", "b.py"], ["S1"], ["/api/v1"], 10, 100)
        new = self._meta(["a.py", "b.py"], ["S1"], ["/api/v1"], 10, 100)
        changes = sd.detect_changes(old, new)
        assert not sd.has_changes(changes)

    def test_new_module(self):
        old = self._meta(["a.py"])
        new = self._meta(["a.py", "c.py"])
        changes = sd.detect_changes(old, new)
        assert changes["new_modules"] == ["c.py"]
        assert sd.has_changes(changes)

    def test_removed_strategy(self):
        old = self._meta(strategies=["S1", "S2"])
        new = self._meta(strategies=["S1"])
        changes = sd.detect_changes(old, new)
        assert changes["removed_strategies"] == ["S2"]
        assert sd.has_changes(changes)

    def test_test_count_change(self):
        old = self._meta(test_count=50)
        new = self._meta(test_count=55)
        changes = sd.detect_changes(old, new)
        assert changes["test_count_change"] == 5
        assert sd.has_changes(changes)

    def test_line_count_not_structural(self):
        old = self._meta(lines=100)
        new = self._meta(lines=200)
        changes = sd.detect_changes(old, new)
        assert changes["line_count_change"] == 100
        assert not sd.has_changes(changes)


class TestChangelogEntry:
    def test_basic_entry(self):
        changes = {
            "new_modules": ["src/new.py"], "removed_modules": [],
            "new_strategies": ["MCTS"], "removed_strategies": [],
            "new_endpoints": [], "removed_endpoints": [],
            "test_count_change": 5, "line_count_change": 100,
        }
        stats = {"total_modules": 10, "total_strategies": 3, "total_endpoints": 5, "total_lines": 1000, "test_count": 50}
        entry = sd.generate_changelog_entry("1.2.0", changes, stats, message="add MCTS")
        assert "v1.2.0" in entry
        assert "add MCTS" in entry
        assert "src/new.py" in entry
        assert "+5" in entry

    def test_default_title(self):
        changes = {
            "new_modules": [], "removed_modules": [],
            "new_strategies": [], "removed_strategies": [],
            "new_endpoints": [], "removed_endpoints": [],
            "test_count_change": 0, "line_count_change": 0,
        }
        stats = {"total_modules": 5, "total_strategies": 2, "total_endpoints": 3, "total_lines": 500, "test_count": 20}
        entry = sd.generate_changelog_entry("0.1.0", changes, stats)
        assert "\u81ea\u52a8\u540c\u6b65" in entry


class TestVersionBump:
    def test_bump_patch(self):
        assert sd._bump_version("1.2.3", "patch") == "1.2.4"
    def test_bump_minor(self):
        assert sd._bump_version("1.2.3", "minor") == "1.3.0"
    def test_bump_major(self):
        assert sd._bump_version("1.2.3", "major") == "2.0.0"


class TestScanning:
    def test_scan_modules(self):
        modules = sd.scan_modules()
        assert isinstance(modules, list)
        assert len(modules) > 0
        for m in modules:
            assert "path" in m and "lines" in m
    def test_scan_strategies(self):
        strategies = sd.scan_strategy_registry()
        assert isinstance(strategies, list)
        assert len(strategies) > 0
    def test_scan_test_count(self):
        count = sd.scan_test_count()
        assert isinstance(count, int)
        assert count > 0
    def test_build_meta(self):
        modules = sd.scan_modules()
        strategies = sd.scan_strategy_registry()
        endpoints = sd.scan_api_endpoints()
        test_count = sd.scan_test_count()
        meta = sd.build_meta(modules, strategies, endpoints, test_count)
        assert "modules" in meta
        assert meta["stats"]["total_modules"] == len(modules)


class TestDocGeneration:
    def test_strategy_table(self):
        strategies = [{"name": "MCTS", "display_name": "MCTS", "description": "test", "type": "tree"}]
        table = sd.generate_strategy_table(strategies)
        assert "MCTS" in table
    def test_api_table(self):
        endpoints = [{"path": "/api/v1/s", "methods": ["GET"]}]
        table = sd.generate_api_table(endpoints)
        assert "GET" in table
    def test_module_map(self):
        modules = [{"path": "src/c.py", "lines": 100, "functions": ["f"], "classes": ["C"], "docstring": "A module"}]
        mmap = sd.generate_module_map(modules)
        assert "c.py" in mmap
    def test_readme_generation(self):
        strategies = [{"name": "TS", "display_name": "TS", "description": "test", "type": "test"}]
        modules = [{"path": "src/t.py", "lines": 50, "functions": [], "classes": []}]
        stats = {"total_modules": 1, "total_strategies": 1, "total_endpoints": 0, "total_lines": 50, "total_classes": 1, "total_functions": 2, "test_count": 5}
        readme = sd.generate_readme(stats, strategies, modules)
        assert "TS" in readme


class TestGitHelpers:
    def test_git_functions_exist(self):
        assert callable(sd._git)
        assert callable(sd._git_has_changes)
        assert callable(sd._git_add_and_commit)
