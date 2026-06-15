# -*- coding: utf-8 -*-
"""
ValueRuntime — 价值运行时

聚合 PositiveValueVector + NegativeValueVector + HardConstraintLayer，
计算 final_score。

final_score = reward_score + positive_score - negative_score

若 hard_constraint == True → 直接 REJECT
"""
import math
from typing import Dict, Any, Optional

from core.value_system.value_vector import PositiveValueVector
from core.value_system.negative_value_vector import NegativeValueVector
from core.value_system.hard_constraint_layer import HardConstraintLayer, ConstraintDecision


class ValueRuntime:
    """价值运行时 — 三层价值防护的聚合入口"""

    def __init__(
        self,
        positive: PositiveValueVector = None,
        negative: NegativeValueVector = None,
        hard_constraint: HardConstraintLayer = None,
    ):
        self.positive = positive or PositiveValueVector()
        self.negative = negative or NegativeValueVector()
        self.hard_constraint = hard_constraint or HardConstraintLayer()

        # 统计
        self._total_evaluations = 0
        self._total_rejections = 0
        self._hard_constraint_rejections = 0

    def evaluate(
        self,
        action_context: Dict[str, Any],
        reward_score: float = 0.0,
    ) -> Dict[str, Any]:
        """评估行为的价值分数

        Args:
            action_context: 行为上下文
            reward_score: 外部奖励分数

        Returns:
            {
                "final_score": float,
                "positive_score": float,
                "negative_score": float,
                "reward_score": float,
                "hard_constraint": ConstraintDecision,
                "rejected": bool,
                "negative_violations": List[str],
            }
        """
        self._total_evaluations += 1

        # 1. Hard Constraint 检查 (最高优先级)
        constraint_decision = self.hard_constraint.evaluate(action_context)
        if not constraint_decision.allowed:
            self._total_rejections += 1
            self._hard_constraint_rejections += 1
            return {
                "final_score": 0.0,
                "positive_score": 0.0,
                "negative_score": 1.0,
                "reward_score": reward_score,
                "hard_constraint": constraint_decision,
                "rejected": True,
                "negative_violations": constraint_decision.violated_constraints,
            }

        # 2. Positive Value 评分
        positive_score = self.positive.score_positive(action_context)

        # 3. Negative Value 评分
        negative_score = self.negative.score_negative(action_context)
        negative_violations = self.negative.detect_violations(action_context)

        # 4. Final Score
        final_score = reward_score + positive_score - negative_score
        final_score = max(0.0, min(1.0, final_score))

        # 5. 如果 negative_score 过高，也拒绝
        rejected = False
        if negative_score > 0.8:
            rejected = True
            self._total_rejections += 1

        return {
            "final_score": final_score,
            "positive_score": positive_score,
            "negative_score": negative_score,
            "reward_score": reward_score,
            "hard_constraint": constraint_decision,
            "rejected": rejected,
            "negative_violations": negative_violations,
        }

    def update_positive_from_identity(self, identity_values: Dict[str, float]) -> None:
        """从 IdentityCore 更新正向价值"""
        self.positive.update_from_identity(identity_values)

    def get_stats(self) -> Dict[str, Any]:
        """返回统计信息"""
        return {
            "total_evaluations": self._total_evaluations,
            "total_rejections": self._total_rejections,
            "hard_constraint_rejections": self._hard_constraint_rejections,
            "rejection_rate": self._total_rejections / max(1, self._total_evaluations),
        }

    def reset_stats(self) -> None:
        """重置统计"""
        self._total_evaluations = 0
        self._total_rejections = 0
        self._hard_constraint_rejections = 0
