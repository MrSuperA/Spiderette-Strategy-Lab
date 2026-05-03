"""Spiderette Strategy Lab — 蜘蛛纸牌移牌策略研究平台"""

from pathlib import Path


def _read_version() -> str:
    """从 pyproject.toml 读取版本号"""
    try:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib
        with open(pyproject, "rb") as f:
            return tomllib.load(f).get("project", {}).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


__version__ = _read_version()
