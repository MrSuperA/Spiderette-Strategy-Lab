"""
路由模块 — Flask Blueprint 拆分

按职责分为 4 个 Blueprint：
  - game_bp:     游戏控制（new-game, step, auto-play, stop, replay）
  - analysis_bp: 分析研究（compare, weakness, calc-factors, genetic, tournament）
  - export_bp:   数据导出（export, history, profile）
  - system_bp:   系统状态（version, status, stream, strategies, tasks）
"""
