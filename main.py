"""
Spiderette Strategy Lab — 主入口
Usage:
    python main.py                  # 启动独立窗口（pywebview + WebView2）
    python main.py --cli            # CLI 模式运行一局
    python main.py --benchmark      # 基准测试
"""

import argparse
import sys
import os
import time
import traceback

# 确保项目根目录在 path 中（支持直接 python main.py 运行）
if not hasattr(sys, '_spiderette_path_set'):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys._spiderette_path_set = True


from src.utils.logging import setup_logging, get_logger
from src.utils.config import get_config
logger = get_logger(__name__)


def run_window(host: str | None = None, port: int | None = None) -> None:
    """启动独立窗口（pywebview + WebView2）"""
    cfg = get_config()
    host = host or cfg.get("server", "host", "127.0.0.1")
    port = port or cfg.get("server", "port", 5679)
    from src.ui.window import run_window as _run_window

    try:
        _run_window(host=host, port=port)
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
    except ImportError as e:
        logger.error("缺少依赖: %s", e)
        logger.info("请执行: pip install pywebview")
        input("\n按回车键退出...")
    except Exception as e:
        logger.error("启动失败: %s", e)
        traceback.print_exc()
        input("\n按回车键退出...")


def run_cli(seed: int = 1, difficulty: int | None = None, strategy_name: str = "mcts") -> None:
    """CLI 模式运行一局"""
    cfg = get_config()
    difficulty = difficulty if difficulty is not None else cfg.get("analysis", "difficulty", 2)
    from src.envs.simulator import SimulatorEnv
    from src.strategy.registry import get_strategy
    from src.core.session import GameSession

    env = SimulatorEnv(seed=seed, difficulty=difficulty)
    strategy = get_strategy(strategy_name)

    logger.info("CLI 启动: seed=%d difficulty=%d strategy=%s", seed, difficulty, strategy.name)
    logger.info("开始运行牌局")

    def on_step(step):
        m = step.move
        if m:
            if m.is_deal:
                print(f"  #{step.step_index:3d} DEAL")
            else:
                print(f"  #{step.step_index:3d} {m.src_col}→{m.dst_col} "
                      f"({m.card_count}张) [{step.elapsed_ms:.0f}ms] "
                      f"legal={step.legal_move_count}")
        else:
            print(f"  #{step.step_index:3d} PASS")

    session = GameSession(env, strategy, max_moves=cfg.get("session", "max_moves", 500), on_step=on_step)
    result = session.run()

    print()
    logger.info("结果: %s (步数=%d, 耗时=%.0fms, 完成=%d/8)", result.outcome.name, result.total_moves, result.total_time_ms, result.completed)



def run_experiment(config_path: str) -> None:
    """运行实验"""
    from src.analysis.runner import ExperimentRunner

    runner = ExperimentRunner(on_progress=lambda p: print(
        f"  [{p['strategy']}] seed={p['seed']} → {p['outcome']} "
        f"({p['done']}/{p['total']})"
    ))

    logger.info("运行实验: %s", config_path)
    result = runner.run_from_config(config_path)
    logger.info(f"[结果] 共 {result.get('total_games', 0)} 局")
    for s in result.get("strategies", []):
        print(f"  {s['name']}: 胜率={s['win_rate']:.1%} "
              f"CI=[{s['win_rate_ci95'][0]:.1%}, {s['win_rate_ci95'][1]:.1%}] "
              f"平均步数={s['avg_moves']:.0f}")


def run_benchmark(
    strategies: list[str],
    difficulty: int = 1,
    num_games: int = 50,
    output_dir: str = "experiments/results",
) -> None:
    """运行基准测试"""
    from src.analysis.runner import BenchmarkRunner
    from src.strategy.registry import get_strategy

    strat_instances = {}
    for name in strategies:
        try:
            strat_instances[name] = get_strategy(name)
        except ValueError:
            print(f"[警告] 未知策略: {name}，跳过")

    if not strat_instances:
        print("[错误] 无有效策略")
        return

    logger.info("基准测试启动")
    print(f"  策略: {', '.join(strat_instances.keys())}")
    print(f"  难度: {difficulty} 花色")
    print(f"  局数: {num_games}")
    print()

    def on_progress(p):
        if p["done"] % 10 == 0 or p["done"] == p["total"]:
            print(f"  [{p['strategy']}] {p['done']}/{p['total']} "
                  f"({p['done']/p['total']:.0%}) {p['outcome']}")

    runner = BenchmarkRunner(on_progress=on_progress)
    runner.run(
        strategies=strat_instances,
        difficulties=[difficulty],
        num_games=num_games,
    )

    logger.info(runner.print_summary())

    out = runner.export(output_dir)
    print(f"\n[Spiderette] 报告已导出: {out}")


def main() -> None:
    setup_logging()
    logger.info("Spiderette Strategy Lab 启动")
    parser = argparse.ArgumentParser(description="Spiderette Strategy Lab")
    parser.add_argument("--cli", action="store_true", help="CLI 模式运行一局")
    parser.add_argument("--experiment", type=str, help="运行实验（TOML 配置路径）")
    parser.add_argument("--benchmark", nargs="+", metavar="STRATEGY",
                        help="运行基准测试（如: --benchmark greedy mcts）")
    parser.add_argument("--bench-difficulty", type=int, default=1,
                        help="基准测试花色数 (1/2/4)")
    parser.add_argument("--bench-games", type=int, default=50,
                        help="基准测试局数")
    parser.add_argument("--bench-output", type=str, default="experiments/results",
                        help="基准测试报告输出目录")
    parser.add_argument("--seed", type=int, default=1, help="牌局种子")
    parser.add_argument("--difficulty", type=int, default=2, help="花色数 (1/2/4)")
    parser.add_argument("--strategy", default="mcts", help="策略名")
    cfg = get_config()
    parser.add_argument("--host", default=cfg.get("server", "host", "127.0.0.1"), help="绑定地址")
    parser.add_argument("--port", type=int, default=cfg.get("server", "port", 5679), help="端口")
    args = parser.parse_args()

    if args.benchmark:
        run_benchmark(
            strategies=args.benchmark,
            difficulty=args.bench_difficulty,
            num_games=args.bench_games,
            output_dir=args.bench_output,
        )
    elif args.experiment:
        run_experiment(args.experiment)
    elif args.cli:
        run_cli(args.seed, args.difficulty, args.strategy)
    else:
        run_window(args.host, args.port)


if __name__ == "__main__":
    main()
