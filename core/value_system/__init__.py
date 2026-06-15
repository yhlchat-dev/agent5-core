# -*- coding: utf-8 -*-
"""
Value System 2.0 — Gene Safety Layer

在 Real Gene Write 前建立三层价值防护：
1. Positive Values（追求什么）
2. Negative Values（避免什么）
3. Hard Constraints（绝对禁止）
"""
from core.value_system.value_vector import PositiveValueVector
from core.value_system.negative_value_vector import NegativeValueVector
from core.value_system.hard_constraint_layer import HardConstraintLayer, ConstraintDecision
from core.value_system.value_runtime import ValueRuntime

__all__ = [
    "PositiveValueVector",
    "NegativeValueVector",
    "HardConstraintLayer",
    "ConstraintDecision",
    "ValueRuntime",
]
