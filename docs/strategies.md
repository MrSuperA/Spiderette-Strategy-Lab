# 策略列表

> 自动生成于 2026-05-04 03:33:50

| 策略名 | 显示名 | 描述 |
|--------|--------|------|
| `mcts` | MCTS | 蒙特卡洛树搜索，200次迭代 |
| `mcts_fast` | MCTS 快速 | 低迭代次数，适合批量 |
| `mcts_deep` | MCTS 深度 | 高迭代次数，高质量 |
| `greedy` | 贪心 | 启发式评分选择最优移动 |
| `random` | 随机 | 随机选择合法移动（基线） |
| `neural` | 神经网络 | MLP 评估策略（需先训练模型） |
| `is_mcts` | 信息集MCTS | 处理暗牌不完美信息的MCTS |
| `puct` | PUCT搜索 | AlphaZero风格PUCT搜索，支持神经网络先验 |
| `name` | display_name | description |