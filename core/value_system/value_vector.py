# -*- coding: utf-8 -*-
"""
PositiveValueVector — 正向价值评分

来源: IdentityCore.current_state.values
评分: action_context 与正向价值的对齐程度
"""
import math
from typing import Dict, Any


class PositiveValueVector:
    """正向价值向量 — 评估行为与追求价值的对齐度"""

    def __init__(self, values: Dict[str, float] = None):
        self.values: Dict[str, float] = values or {
            "accuracy": 1.0,
            "helpfulness": 1.0,
            "safety": 1.0,
            "creativity": 0.8,
            "depth": 0.8,
            "autonomy": 0.7,
        }

    def score_positive(self, action_context: Dict[str, Any]) -> float:
        """计算行为与正向价值的对齐分数

        Args:
            action_context: 行为上下文，应包含与 values 对应的键值

        Returns:
            0.0 ~ 1.0 的对齐分数
        """
        if not action_context:
            return 0.5

        # 从 action_context 提取与 values 对齐的维度
        common_keys = set(self.values.keys()) & set(action_context.keys())
        if not common_keys:
            return 0.5

        # 加权对齐: 每个维度的 action_context 值 × value 权重
        weighted_sum = 0.0
        weight_sum = 0.0
        for k in common_keys:
            v = self.values[k]
            a = action_context[k]
            if isinstance(a, (int, float)):
                weighted_sum += a * v
                weight_sum += v

        if weight_sum < 1e-8:
            return 0.5

        # 归一化到 0~1
        score = weighted_sum / weight_sum
        return max(0.0, min(1.0, score))

    def update_from_identity(self, identity_values: Dict[str, float]) -> None:
        """从 IdentityCore 更新正向价值"""
        for k, v in identity_values.items():
            if k in self.values:
                self.values[k] = v

    def get_vector(self) -> Dict[str, float]:
        """返回当前正向价值向量"""
        return dict(self.values)
