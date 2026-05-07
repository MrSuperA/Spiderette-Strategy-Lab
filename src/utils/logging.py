"""
统一日志系统 - 分类输出 + 统一管理

设计原则：
  1. 所有模块通过 get_logger(__name__) 获取 logger，自动继承全局配置
  2. 日志按模块分类存储：app.log（全量）、error.log（错误）、strategy.log（策略决策）
  3. 控制台输出简洁友好，文件输出包含完整上下文
  4. 打包环境下日志写入 exe 同级 logs/ 目录，开发环境写入项目根目录 logs/

用法：
  from src.utils.logging import setup_logging, get_logger
  setup_logging()  # 程序入口调用一次
  logger = get_logger(__name__)
  logger.info("开始处理")
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from src.utils.paths import get_data_dir


# ===================================================
#  日志级别常量
# ===================================================

# 策略决策专用级别（比 DEBUG 更细，用于记录每步选择）
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


# ===================================================
#  格式化器
# ===================================================

# 控制台：简洁，只保留关键信息
CONSOLE_FORMAT = "%(asctime)s [%(levelname).1s] %(name)s: %(message)s"
CONSOLE_DATE_FORMAT = "%H:%M:%S"

# 文件：完整上下文，含模块路径和行号
FILE_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s (%(filename)s:%(lineno)d) -- %(message)s"
FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 错误日志：与文件格式相同
ERROR_FORMAT = FILE_FORMAT


# ===================================================
#  日志目录
# ===================================================

_LOGS_DIR: Optional[Path] = None


def get_logs_dir() -> Path:
    """获取日志目录（懒创建）"""
    global _LOGS_DIR
    if _LOGS_DIR is None:
        _LOGS_DIR = get_data_dir() / "logs"
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return _LOGS_DIR


# ===================================================
#  模块级 logger 配置
# ===================================================

# 各模块的日志级别覆盖（模块前缀 -> 级别）
_MODULE_LEVEL_OVERRIDES: dict[str, int] = {}


def set_module_level(module_prefix: str, level: int) -> None:
    """
    动态调整某个模块的日志级别

    Args:
        module_prefix: 模块前缀，如 "src.strategy"
        level: 日志级别，如 logging.DEBUG
    """
    _MODULE_LEVEL_OVERRIDES[module_prefix] = level
    logger = logging.getLogger(module_prefix)
    logger.setLevel(level)


# ===================================================
#  初始化
# ===================================================

_initialized = False


def setup_logging(
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_to_file: bool = True,
    max_bytes: int = 5 * 1024 * 1024,  # 5MB per file
    backup_count: int = 3,
) -> None:
    """
    初始化全局日志系统（整个程序只需调用一次）

    Args:
        console_level: 控制台输出级别（默认 INFO）
        file_level: 文件输出级别（默认 DEBUG）
        log_to_file: 是否写入日志文件（打包环境下可关闭）
        max_bytes: 单个日志文件最大大小（默认 5MB）
        backup_count: 保留的历史日志文件数（默认 3）
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger("spiderette")
    root.setLevel(logging.DEBUG)  # 根 logger 捕获所有级别，由 handler 过滤

    # 防止重复添加 handler
    if root.handlers:
        root.handlers.clear()

    # -- 控制台 handler --
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt=CONSOLE_DATE_FORMAT))
    root.addHandler(console)

    if not log_to_file:
        return

    logs_dir = get_logs_dir()

    # -- 主日志文件（全量，按大小轮转）--
    app_log = logging.handlers.RotatingFileHandler(
        logs_dir / "app.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    app_log.setLevel(file_level)
    app_log.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=FILE_DATE_FORMAT))
    root.addHandler(app_log)

    # -- 错误日志文件（仅 ERROR+）--
    error_log = logging.handlers.RotatingFileHandler(
        logs_dir / "error.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_log.setLevel(logging.ERROR)
    error_log.setFormatter(logging.Formatter(ERROR_FORMAT, datefmt=FILE_DATE_FORMAT))
    root.addHandler(error_log)

    # -- 策略决策日志（独立文件，方便分析策略行为）--
    strategy_log = logging.handlers.RotatingFileHandler(
        logs_dir / "strategy.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    strategy_log.setLevel(logging.DEBUG)
    strategy_log.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=FILE_DATE_FORMAT))
    # 只接收策略相关 logger 的日志
    strategy_log.addFilter(_ModuleFilter("spiderette.strategy"))
    root.addHandler(strategy_log)

    # -- 训练日志（RL/迭代引擎，独立文件）--
    training_log = logging.handlers.RotatingFileHandler(
        logs_dir / "training.log",
        maxBytes=max_bytes * 2,  # 训练日志更大
        backupCount=backup_count,
        encoding="utf-8",
    )
    training_log.setLevel(logging.DEBUG)
    training_log.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=FILE_DATE_FORMAT))
    training_log.addFilter(_ModuleFilter("spiderette.rl", "spiderette.iteration"))
    root.addHandler(training_log)

    root.info("日志系统初始化完成 -> %s", logs_dir)


class _ModuleFilter(logging.Filter):
    """只允许指定模块前缀的日志通过"""

    def __init__(self, *prefixes: str):
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return any(record.name.startswith(p) for p in self._prefixes)


# ===================================================
#  公共 API
# ===================================================

def get_logger(name: str) -> logging.Logger:
    """
    获取模块级 logger

    用法：
        logger = get_logger(__name__)
        logger.info("开始处理牌局")
        logger.debug("合法移动: %s", moves)
        logger.error("策略执行失败", exc_info=True)

    所有 logger 自动继承 spiderette 根 logger 的配置，
    无需手动添加 handler 或设置级别。
    """
    # 将 src.xxx.yyy 映射为 spiderette.xxx.yyy（统一命名空间）
    if name.startswith("src."):
        name = "spiderette." + name[4:]
    elif name == "src":
        name = "spiderette"

    logger = logging.getLogger(name)

    # 应用模块级覆盖
    for prefix, level in _MODULE_LEVEL_OVERRIDES.items():
        if name.startswith(prefix):
            logger.setLevel(level)
            break

    return logger


def trace(self, msg, *args, **kwargs):
    """自定义 TRACE 级别方法（绑定到 Logger 上）"""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, msg, args, **kwargs)


# 绑定 trace 方法到 Logger 类
logging.Logger.trace = trace  # type: ignore[attr-defined]


# ===================================================
#  便捷函数
# ===================================================

def log_exception(logger: logging.Logger, msg: str = "异常发生") -> None:
    """
    统一的异常日志记录（自动附带完整 traceback）

    用法：
        try:
            risky_operation()
        except Exception:
            log_exception(logger, "策略执行失败")
    """
    logger.error(msg, exc_info=True)


def log_performance(logger: logging.Logger, operation: str, elapsed_ms: float, **extra) -> None:
    """
    性能日志（记录操作耗时）

    用法：
        log_performance(logger, "MCTS搜索", 45.2, nodes=1200, depth=8)
    """
    extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
    logger.info("[性能] %s: %.1fms %s", operation, elapsed_ms, extra_str)


def log_strategy_decision(
    logger: logging.Logger,
    step: int,
    move,
    candidates: list = None,
    elapsed_ms: float = 0,
) -> None:
    """
    策略决策日志（记录每步选择和候选）

    用法：
        log_strategy_decision(logger, step=42, move=chosen_move,
                             candidates=legal_moves, elapsed_ms=12.3)
    """
    move_str = str(move) if move else "deal"
    if candidates:
        cand_str = ", ".join(str(m) for m in candidates[:5])
        if len(candidates) > 5:
            cand_str += f" ... (+{len(candidates) - 5})"
    else:
        cand_str = "--"
    logger.debug(
        "[决策] step=%d move=%s candidates=[%s] elapsed=%.1fms",
        step, move_str, cand_str, elapsed_ms,
    )
