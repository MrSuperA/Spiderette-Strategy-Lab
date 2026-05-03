"""
路径解析工具 — 统一处理开发环境和 PyInstaller 打包环境的路径

打包环境（单文件 exe）：
  - sys.executable = exe 所在路径
  - __file__ = 临时解压目录（退出时删除，不可用于持久化）
  - 持久化数据存储在 exe 同级的 spiderette_data/ 目录

开发环境：
  - __file__ = 源码目录
  - 持久化数据存储在项目根目录下
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否在 PyInstaller 打包环境中运行"""
    return getattr(sys, 'frozen', False)


def get_app_root() -> Path:
    """
    获取应用根目录

    - 打包环境：exe 所在目录
    - 开发环境：项目根目录
    """
    if is_frozen():
        return Path(sys.executable).parent
    else:
        # src/utils/paths.py → 向上 3 级到项目根
        return Path(__file__).parent.parent.parent


def get_data_dir() -> Path:
    """
    获取持久化数据目录

    - 打包环境：exe 同级的 spiderette_data/
    - 开发环境：项目根目录

    所有运行时产生的数据（导出文件、迭代记录、模型等）都存储在此目录下。
    """
    if is_frozen():
        data_dir = get_app_root() / "spiderette_data"
    else:
        data_dir = get_app_root()

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_output_dir(subdir: str = "") -> Path:
    """
    获取输出子目录（自动创建）

    Args:
        subdir: 子目录名

    Returns:
        完整路径
    """
    base = get_data_dir()
    if subdir:
        out = base / subdir
    else:
        out = base
    out.mkdir(parents=True, exist_ok=True)
    return out


def get_experiments_dir() -> Path:
    """实验结果输出目录"""
    return get_output_dir("experiments/results")


def get_iterations_dir() -> Path:
    """迭代记录输出目录"""
    return get_output_dir("iterations")


def get_models_dir() -> Path:
    """模型保存目录"""
    return get_output_dir("models")


def get_export_dir() -> Path:
    """用户导出目录（首次导出时由用户选择，后续复用）"""
    return get_output_dir("exports")
