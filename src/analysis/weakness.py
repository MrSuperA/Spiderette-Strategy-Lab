"""
策略弱点自动检测 — 基于量化因子识别策略短板
参考：阈值比较 + 行业基准 + 交叉验证
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Weakness:
    """一个弱点"""
    factor: str             # 因子名
    display_name: str       # 显示名
    score: float            # 当前得分
    threshold: float        # 阈值
    severity: str           # "high" / "medium" / "low"
    suggestion: str         # 改进建议

    @classmethod
    def from_dict(cls, data: dict) -> Weakness:
        return cls(
            factor=data["factor"],
            display_name=data.get("display_name", ""),
            score=data.get("score", 0.0),
            threshold=data.get("threshold", 0.0),
            severity=data.get("severity", "low"),
            suggestion=data.get("suggestion", ""),
        )


@dataclass
class WeaknessReport:
    """弱点报告"""
    strategy_name: str
    weaknesses: list[Weakness] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    overall_score: float = 0.0   # 综合得分 (0-1)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "overall_score": round(self.overall_score, 3),
            "weaknesses": [
                {
                    "factor": w.factor,
                    "display_name": w.display_name,
                    "score": round(w.score, 3),
                    "threshold": round(w.threshold, 3),
                    "severity": w.severity,
                    "suggestion": w.suggestion,
                }
                for w in self.weaknesses
            ],
            "strengths": self.strengths,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WeaknessReport:
        return cls(
            strategy_name=data.get("strategy", data.get("strategy_name", "")),
            weaknesses=[Weakness.from_dict(w) for w in data.get("weaknesses", [])],
            strengths=data.get("strengths", []),
            overall_score=data.get("overall_score", 0.0),
        )


# 弱点阈值定义（基于行业基准）
THRESHOLDS = {
    "suit_preservation": {
        "display_name": "花色保持",
        "low": 0.3, "medium": 0.5,
        "param_hint": "suit_weight",
        "low_suggestion": "花色保持率极低，策略完全忽略花色一致性。建议在启发式评分中增加花色匹配权重。",
        "medium_suggestion": "花色保持率偏低。建议优先选择同花色移动，特别是在序列构建阶段。",
    },
    "exposure_willingness": {
        "display_name": "翻牌意愿",
        "low": 0.1, "medium": 0.3,
        "param_hint": "flip_bonus",
        "low_suggestion": "翻牌意愿极低，策略过于保守。建议适当增加翻牌移动的优先级，特别是当暗牌数量较多时。",
        "medium_suggestion": "翻牌意愿偏低。建议在无同花色移动时优先翻牌。",
    },
    "sequence_building": {
        "display_name": "序列构建",
        "low": 0.2, "medium": 0.4,
        "param_hint": "sequence_weight",
        "low_suggestion": "序列构建能力弱。建议增加序列长度在评分中的权重，优先延续已有序列。",
        "medium_suggestion": "序列构建有提升空间。建议关注 K→A 完整路径的构建。",
    },
    "empty_column_usage": {
        "display_name": "空列利用",
        "low": 0.1, "medium": 0.3,
        "param_hint": "empty_column_weight",
        "low_suggestion": "空列利用率极低。建议将空列视为战略资源，优先用于重组关键序列。",
        "medium_suggestion": "空列利用不足。建议在有空列时优先进行大规模移牌重组。",
    },
    "deal_timing": {
        "display_name": "发牌时机",
        "low": 0.1, "medium": 0.3,
        "param_hint": "deal_threshold",
        "low_suggestion": "发牌时机过于保守。建议在合法移动较少时尽早发牌，避免陷入局部最优。",
        "medium_suggestion": "发牌时机可优化。建议在牌面清理后发牌，最大化发牌收益。",
    },
    "reversibility_preference": {
        "display_name": "可逆偏好",
        "low": 0.3, "medium": 0.5,
        "param_hint": "reversibility_weight",
        "low_suggestion": "可逆性偏好低，策略倾向于不可逆操作。建议优先选择不翻牌的移动，保持局面灵活性。",
        "medium_suggestion": "可逆性偏好偏低。建议在决策时考虑移动的可逆性。",
    },
    "risk_tolerance": {
        "display_name": "风险容忍",
        "low": 0.2, "medium": 0.5,
        "param_hint": "risk_factor",
        "low_suggestion": "风险容忍度低，策略过于保守。建议在有明确收益时敢于冒险。",
        "medium_suggestion": "风险容忍度偏高。建议在不确定时选择更安全的移动。",
    },
    "decision_consistency": {
        "display_name": "决策一致",
        "low": 0.3, "medium": 0.5,
        "param_hint": "temperature",
        "low_suggestion": "决策一致性低，策略行为不稳定。建议增加决策函数的确定性，减少随机因素。",
        "medium_suggestion": "决策一致性有提升空间。建议优化评分函数的区分度。",
    },
}


def detect_weaknesses(strategy_name: str, factors: dict[str, float]) -> WeaknessReport:
    """
    检测策略弱点

    Args:
        strategy_name: 策略名
        factors: {因子名: 得分} 字典

    Returns:
        WeaknessReport 弱点报告
    """
    report = WeaknessReport(strategy_name=strategy_name)

    scores = []
    for factor_name, score in factors.items():
        config = THRESHOLDS.get(factor_name)
        if not config:
            continue

        scores.append(score)

        if score < config["low"]:
            report.weaknesses.append(Weakness(
                factor=factor_name,
                display_name=config["display_name"],
                score=score,
                threshold=config["low"],
                severity="high",
                suggestion=config["low_suggestion"],
            ))
        elif score < config["medium"]:
            report.weaknesses.append(Weakness(
                factor=factor_name,
                display_name=config["display_name"],
                score=score,
                threshold=config["medium"],
                severity="medium",
                suggestion=config["medium_suggestion"],
            ))
        else:
            report.strengths.append(config["display_name"])

    # 综合得分
    report.overall_score = sum(scores) / len(scores) if scores else 0.0

    # 按严重程度排序
    severity_order = {"high": 0, "medium": 1, "low": 2}
    report.weaknesses.sort(key=lambda w: severity_order.get(w.severity, 3))

    return report


def suggest_params(strategy_name: str, report: WeaknessReport) -> dict:
    """
    根据弱点报告生成策略参数建议

    为每个识别出的弱点，根据其严重程度生成对应的参数调整建议。
    返回的字典可直接传给 get_strategy(**params) 使用。

    Args:
        strategy_name: 策略名（保留用于未来策略特定逻辑）
        report: 弱点报告

    Returns:
        参数建议字典 {param_name: suggested_value}
    """
    params: dict = {}

    for w in report.weaknesses:
        config = THRESHOLDS.get(w.factor)
        if not config or "param_hint" not in config:
            continue

        hint = config["param_hint"]

        # 根据因子类型和严重程度生成参数值
        if hint == "temperature":
            # 温度参数：严重程度越高，温度越低（更确定性）
            params[hint] = 0.3 if w.severity == "high" else 0.6
        elif hint == "deal_threshold":
            # 发牌阈值：越严重越需要降低阈值（更早发牌）
            params[hint] = 0.2 if w.severity == "high" else 0.4
        elif hint == "risk_factor":
            # 风险因子：根据严重程度调整
            params[hint] = 0.7 if w.severity == "high" else 0.5
        else:
            # 权重类参数：严重程度越高，提升权重越多
            base = 1.0
            if w.severity == "high":
                params[hint] = base * 2.0
            elif w.severity == "medium":
                params[hint] = base * 1.5

    return params
