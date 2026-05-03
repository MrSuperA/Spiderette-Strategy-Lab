"""
神经网络评估策略 — 使用 MLP 评估棋盘状态
替代 MCTS 中的随机 rollout，用训练好的网络预测胜率
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.core.types import GameState, Move, Rules, Strategy
from src.core.rules import RulesEngine
from src.core.session import GameSession
from src.envs.simulator import SimulatorEnv


# ═══════════════════════════════════════════════════════════
#  特征提取
# ═══════════════════════════════════════════════════════════

def extract_features(state: GameState) -> list[float]:
    """
    提取棋盘状态特征向量（约 60 维）

    特征组成：
    - 每列 5 维 × 10 列 = 50 维
    - 全局特征 8 维
    """
    features = []
    cols = state.columns

    for col in cols:
        cards = col.cards
        face_up = [c for c in cards if c.face_up]
        face_down = col.face_down_count

        if not cards:
            features.extend([0.0, 0.0, 0.0, 0.0, 0.0])
            continue

        # 1. 顶牌 rank (归一化到 0-1)
        top_rank = face_up[-1].rank / 13.0 if face_up else 0.0
        features.append(top_rank)

        # 2. 明牌数 / 总牌数
        features.append(len(face_up) / max(1, len(cards)))

        # 3. 最长同花色序列长度 / 13
        seq_len = 0
        for i in range(len(face_up) - 1, 0, -1):
            if (face_up[i].suit == face_up[i-1].suit and
                face_up[i].rank == face_up[i-1].rank - 1):
                seq_len += 1
            else:
                break
        if face_up:
            seq_len += 1
        features.append(seq_len / 13.0)

        # 4. 列长度 / 20
        features.append(len(cards) / 20.0)

        # 5. 花色一致性（顶牌花色占比）
        if face_up:
            top_suit = face_up[-1].suit
            same = sum(1 for c in face_up if c.suit == top_suit)
            features.append(same / len(face_up))
        else:
            features.append(0.0)

    # 全局特征
    total_face_down = sum(c.face_down_count for c in cols)
    total_face_up = sum(len([c for c in col.cards if c.face_up]) for col in cols)
    empty_cols = sum(1 for c in cols if c.is_empty)

    features.append(len(state.stock) / 50.0)       # 发牌剩余
    features.append(state.completed / 8.0)          # 完成进度
    features.append(total_face_down / 50.0)         # 暗牌比例
    features.append(total_face_up / 54.0)           # 明牌比例
    features.append(empty_cols / 10.0)              # 空列比例
    features.append(state.move_count / 500.0)       # 步数进度
    features.append(state.difficulty / 4.0)         # 难度
    features.append(1.0 if state.difficulty == 1 else 0.0)  # 1花色标志

    return features


# ═══════════════════════════════════════════════════════════
#  简易 MLP（纯 numpy 实现，不依赖 PyTorch）
# ═══════════════════════════════════════════════════════════

class SimpleMLP:
    """
    简易多层感知器 — 纯 numpy 实现
    结构: input → hidden1(128) → hidden2(64) → output(1)
    """

    def __init__(self, input_size: int = 58, hidden1: int = 128, hidden2: int = 64):
        import numpy as np
        self.np = np
        # Xavier 初始化
        self.W1 = np.random.randn(input_size, hidden1) * np.sqrt(2.0 / input_size)
        self.b1 = np.zeros(hidden1)
        self.W2 = np.random.randn(hidden1, hidden2) * np.sqrt(2.0 / hidden1)
        self.b2 = np.zeros(hidden2)
        self.W3 = np.random.randn(hidden2, 1) * np.sqrt(2.0 / hidden2)
        self.b3 = np.zeros(1)

    def predict(self, features: list[float]) -> float:
        """预测胜率 [0, 1]"""
        x = self.np.array(features, dtype=self.np.float32).reshape(1, -1)
        h1 = self.np.maximum(0, x @ self.W1 + self.b1)       # ReLU
        h2 = self.np.maximum(0, h1 @ self.W2 + self.b2)      # ReLU
        out = 1 / (1 + self.np.exp(-(h2 @ self.W3 + self.b3)))  # Sigmoid
        return float(out[0, 0])

    def predict_batch(self, features_list: list[list[float]]) -> list[float]:
        """批量预测"""
        x = self.np.array(features_list, dtype=self.np.float32)
        h1 = self.np.maximum(0, x @ self.W1 + self.b1)
        h2 = self.np.maximum(0, h1 @ self.W2 + self.b2)
        out = 1 / (1 + self.np.exp(-(h2 @ self.W3 + self.b3)))
        return out.flatten().tolist()

    def save(self, path: str):
        import numpy as np
        np.savez(path, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2, W3=self.W3, b3=self.b3)

    def load(self, path: str):
        import numpy as np
        data = np.load(path)
        self.W1, self.b1 = data["W1"], data["b1"]
        self.W2, self.b2 = data["W2"], data["b2"]
        self.W3, self.b3 = data["W3"], data["b3"]


# ═══════════════════════════════════════════════════════════
#  训练器
# ═══════════════════════════════════════════════════════════

class NeuralTrainer:
    """
    神经网络训练器

    流程：
    1. 用现有策略玩游戏，收集 (state, outcome) 数据
    2. 训练 MLP 预测胜率
    3. 导出模型供 NeuralStrategy 使用
    """

    def __init__(self, model: Optional[SimpleMLP] = None):
        self.model = model or SimpleMLP()

    def collect_data(
        self,
        strategy_name: str = "greedy",
        difficulty: int = 1,
        num_games: int = 100,
        sample_rate: float = 0.1,
    ) -> tuple[list[list[float]], list[float]]:
        """收集训练数据"""
        from src.strategy.registry import get_strategy
        strategy = get_strategy(strategy_name)
        features_list = []
        labels = []
        rng = random.Random(42)

        for seed in range(1, num_games + 1):
            env = SimulatorEnv(seed=seed, difficulty=difficulty)
            session = GameSession(env, strategy, max_moves=300)
            result = session.run()

            # 从每局中采样决策点
            for step in result.steps:
                if rng.random() < sample_rate:
                    feat = extract_features(step.state)
                    features_list.append(feat)
                    labels.append(1.0 if result.completed >= 8 else result.completed / 8.0)

        return features_list, labels

    def train(
        self,
        features: list[list[float]],
        labels: list[float],
        epochs: int = 50,
        lr: float = 0.001,
        batch_size: int = 64,
    ) -> list[float]:
        """训练模型"""
        import numpy as np

        X = np.array(features, dtype=np.float32)
        y = np.array(labels, dtype=np.float32).reshape(-1, 1)
        n = len(X)
        losses = []

        for epoch in range(epochs):
            # 随机打乱
            idx = np.random.permutation(n)
            X_shuffled = X[idx]
            y_shuffled = y[idx]

            epoch_loss = 0.0
            for i in range(0, n, batch_size):
                X_batch = X_shuffled[i:i + batch_size]
                y_batch = y_shuffled[i:i + batch_size]

                # 前向传播
                h1 = np.maximum(0, X_batch @ self.model.W1 + self.model.b1)
                h2 = np.maximum(0, h1 @ self.model.W2 + self.model.b2)
                out = 1 / (1 + np.exp(-(h2 @ self.model.W3 + self.model.b3)))

                # 损失 (MSE)
                loss = np.mean((out - y_batch) ** 2)
                epoch_loss += loss

                # 反向传播
                d_out = 2 * (out - y_batch) / len(X_batch)
                d_sig = out * (1 - out)
                d_out = d_out * d_sig

                dW3 = h2.T @ d_out
                db3 = np.sum(d_out, axis=0)

                dh2 = d_out @ self.model.W3.T
                dh2[h2 <= 0] = 0

                dW2 = h1.T @ dh2
                db2 = np.sum(dh2, axis=0)

                dh1 = dh2 @ self.model.W2.T
                dh1[h1 <= 0] = 0

                dW1 = X_batch.T @ dh1
                db1 = np.sum(dh1, axis=0)

                # 更新权重
                self.model.W3 -= lr * dW3
                self.model.b3 -= lr * db3
                self.model.W2 -= lr * dW2
                self.model.b2 -= lr * db2
                self.model.W1 -= lr * dW1
                self.model.b1 -= lr * db1

            avg_loss = epoch_loss / (n // batch_size + 1)
            losses.append(avg_loss)

        return losses

    def save_model(self, path: str):
        self.model.save(path)

    def load_model(self, path: str):
        self.model.load(path)


# ═══════════════════════════════════════════════════════════
#  神经网络策略
# ═══════════════════════════════════════════════════════════

class NeuralStrategy:
    """
    神经网络评估策略 — 用训练好的 MLP 评估每个移动的后续状态

    接入方式：
        strategy = NeuralStrategy("model.npz")
        move = strategy.choose(state, rules)
    """

    def __init__(self, model_path: Optional[str] = None, model: Optional[SimpleMLP] = None):
        self._model = model or SimpleMLP()
        if model_path and os.path.exists(model_path):
            self._model.load(model_path)

    @property
    def name(self) -> str:
        return "neural"

    def choose(self, state: GameState, rules: Rules) -> Optional[Move]:
        if rules.is_terminal(state).value > 0:
            return None
        legal = rules.legal_moves(state)
        if not legal:
            return None
        if len(legal) == 1:
            return legal[0]

        # 评估每个移动的后续状态（模拟执行后提取新状态特征）
        best_move = None
        best_score = -1.0

        for move in legal:
            new_state = rules.apply_move(state, move)
            feat = extract_features(new_state)

            score = self._model.predict(feat)
            if score > best_score:
                best_score = score
                best_move = move

        return best_move
