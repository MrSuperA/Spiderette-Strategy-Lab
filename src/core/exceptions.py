"""
统一异常体系 — 所有自定义异常的根
层级：SpideretteError → GameStateError / StrategyError / AnalysisError / ConfigError
"""


class SpideretteError(Exception):
    """项目根异常"""


class GameStateError(SpideretteError):
    """游戏状态相关错误（非法移动、非法状态等）"""


class StrategyError(SpideretteError):
    """策略相关错误（未知策略、策略执行失败等）"""


class AnalysisError(SpideretteError):
    """分析相关错误（数据不足、计算失败等）"""


class ConfigError(SpideretteError):
    """配置相关错误（参数无效、配置文件格式错误等）"""
