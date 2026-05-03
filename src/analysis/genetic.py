"""
遗传算法优化器 — 自动进化最优策略参数
种群 → 适应度评估 → 选择 → 交叉 → 变异 → 迭代
"""

from __future__ import annotations

import json
import random
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.session import GameSession
from src.core.types import Strategy
from src.envs.simulator import SimulatorEnv
from src.strategy.registry import get_strategy
from src.analysis.utils import run_single_game


@dataclass
class Gene:
    """一个个体（参数组合）"""
    params: dict
    fitness: float = 0.0
    win_rate: float = 0.0
    avg_completed: float = 0.0

    def to_dict(self) -> dict:
        return {"params": self.params, "fitness": round(self.fitness, 4),
                "win_rate": round(self.win_rate, 4), "avg_completed": round(self.avg_completed, 2)}

    @classmethod
    def from_dict(cls, data: dict) -> Gene:
        return cls(
            params=data["params"],
            fitness=data.get("fitness", 0.0),
            win_rate=data.get("win_rate", 0.0),
            avg_completed=data.get("avg_completed", 0.0),
        )


@dataclass
class GAResult:
    """进化结果"""
    best: Gene
    generations: int
    strategy_name: str = ""
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"best": self.best.to_dict(), "generations": self.generations,
                "strategy_name": self.strategy_name, "history": self.history}

    @classmethod
    def from_dict(cls, data: dict) -> GAResult:
        return cls(
            best=Gene.from_dict(data["best"]),
            generations=data["generations"],
            strategy_name=data.get("strategy_name", ""),
            history=data.get("history", []),
        )


class GeneticOptimizer:
    """
    遗传算法优化器

    用法::

        ga = GeneticOptimizer("mcts", {
            "iterations": [100, 200, 500],
            "time_limit": [0.1, 0.2, 0.5],
            "exploration": [0.8, 1.0, 1.4, 2.0],
        })
        result = ga.evolve(difficulty=1, pop_size=10, generations=20)
    """

    def __init__(self, strategy_name: str, param_space: dict[str, list]):
        self.strategy_name = strategy_name
        self.param_space = param_space  # {param_name: [values]}
        self.param_names = list(param_space.keys())

    def evolve(
        self,
        difficulty: int = 1,
        pop_size: int = 10,
        generations: int = 20,
        games_per_eval: int = 10,
        mutation_rate: float = 0.2,
        crossover_rate: float = 0.7,
        elite_count: int = 2,
        seed: int = 42,
    ) -> GAResult:
        """运行遗传算法"""
        rng = random.Random(seed)
        eval_seeds = list(range(1, games_per_eval + 1))

        # 初始化种群
        population = [self._random_individual(rng) for _ in range(pop_size)]

        # 评估初始种群
        for gene in population:
            gene.fitness, gene.win_rate, gene.avg_completed = self._evaluate(
                gene.params, difficulty, eval_seeds
            )

        history = []
        best_ever = max(population, key=lambda g: g.fitness)

        for gen in range(generations):
            # 选择
            parents = self._tournament_select(population, pop_size, rng)

            # 交叉 + 变异
            offspring = []
            for i in range(0, len(parents) - 1, 2):
                if rng.random() < crossover_rate:
                    c1, c2 = self._crossover(parents[i], parents[i + 1], rng)
                else:
                    c1, c2 = Gene(params=dict(parents[i].params)), Gene(params=dict(parents[i + 1].params))
                self._mutate(c1, rng, mutation_rate)
                self._mutate(c2, rng, mutation_rate)
                offspring.extend([c1, c2])

            # 评估后代
            for gene in offspring[:pop_size - elite_count]:
                gene.fitness, gene.win_rate, gene.avg_completed = self._evaluate(
                    gene.params, difficulty, eval_seeds
                )

            # 精英保留
            elite = sorted(population, key=lambda g: -g.fitness)[:elite_count]
            population = elite + offspring[:pop_size - elite_count]

            gen_best = max(population, key=lambda g: g.fitness)
            if gen_best.fitness > best_ever.fitness:
                best_ever = Gene(params=dict(gen_best.params), fitness=gen_best.fitness,
                               win_rate=gen_best.win_rate, avg_completed=gen_best.avg_completed)

            gen_stats = {
                "generation": gen + 1,
                "best_fitness": round(gen_best.fitness, 4),
                "avg_fitness": round(sum(g.fitness for g in population) / len(population), 4),
                "best_win_rate": round(gen_best.win_rate, 4),
            }
            history.append(gen_stats)

        return GAResult(best=best_ever, generations=generations,
                        strategy_name=self.strategy_name, history=history)

    def _random_individual(self, rng: random.Random) -> Gene:
        params = {name: rng.choice(values) for name, values in self.param_space.items()}
        return Gene(params=params)

    def _evaluate(self, params: dict, difficulty: int, seeds: list[int]) -> tuple[float, float, float]:
        """评估一组参数的适应度"""
        try:
            strategy = get_strategy(self.strategy_name, **params)
        except Exception:
            return 0.0, 0.0, 0.0

        wins = 0
        total_completed = 0
        for seed in seeds:
            try:
                result = run_single_game(seed, difficulty, strategy, max_moves=300)
                if result.completed >= 8:
                    wins += 1
                total_completed += result.completed
            except Exception:
                continue

        win_rate = wins / len(seeds) if seeds else 0.0
        avg_completed = total_completed / len(seeds) if seeds else 0.0
        fitness = win_rate * 100 + avg_completed * 5
        return fitness, win_rate, avg_completed

    def _tournament_select(self, population: list[Gene], count: int, rng: random.Random) -> list[Gene]:
        selected = []
        for _ in range(count):
            a, b = rng.sample(population, 2)
            selected.append(a if a.fitness > b.fitness else b)
        return selected

    def _crossover(self, g1: Gene, g2: Gene, rng: random.Random) -> tuple[Gene, Gene]:
        c1_params, c2_params = {}, {}
        for name in self.param_names:
            if rng.random() < 0.5:
                c1_params[name], c2_params[name] = g1.params[name], g2.params[name]
            else:
                c1_params[name], c2_params[name] = g2.params[name], g1.params[name]
        return Gene(params=c1_params), Gene(params=c2_params)

    def _mutate(self, gene: Gene, rng: random.Random, rate: float):
        for name, values in self.param_space.items():
            if rng.random() < rate:
                gene.params[name] = rng.choice(values)

    def export(self, result: GAResult, output_dir: str | Path) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"ga_{self.strategy_name}_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        return path
