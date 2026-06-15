# -*- coding: utf-8 -*-
"""
ConstitutionRuntime — 统一价值接口

向 Policy / Goal / Planner / Pattern Learning / Reward Engine 提供唯一价值来源。
"""
import logging
from typing import Dict, Any, Optional

from core.constitution.constitution_vector import ConstitutionVector
from core.constitution.constitution_evaluator import ConstitutionEvaluator, ConstitutionScore
from core.constitution.constitution_event import ConstitutionEventLog


class ConstitutionRuntime:
    """Constitution Runtime — 系统唯一价值真源的运行时接口

    所有模块通过此接口获取价值判断，而非各自维护独立逻辑。

    提供：
    - evaluate(): 通用评估
    - score_action(): 动作评分
    - score_goal(): 目标评分
    - score_pattern(): 模式评分
    """

    def __init__(
        self,
        vector: Optional[ConstitutionVector] = None,
        evaluator: Optional[ConstitutionEvaluator] = None,
    ):
        self.vector = vector or ConstitutionVector()
        self.evaluator = evaluator or ConstitutionEvaluator()
        self.event_log = ConstitutionEventLog()
        self.logger = logging.getLogger("ConstitutionRuntime")

    def evaluate(
        self,
        success: bool = True,
        risk_level: float = 0.0,
        accuracy: float = 1.0,
        efficiency: float = 1.0,
        exploration: float = 0.0,
        goal_achievement: float = 1.0,
        persistence_shown: bool = True,
        strategic_value: float = 0.5,
        context: str = "",
    ) -> float:
        """通用评估 — 返回 Constitution 加权总分"""
        score = self.evaluator.evaluate(
            success=success,
            risk_level=risk_level,
            accuracy=accuracy,
            efficiency=efficiency,
            exploration=exploration,
            goal_achievement=goal_achievement,
            persistence_shown=persistence_shown,
            strategic_value=strategic_value,
            context=context,
        )
        total = self.vector.score(score.scores)
        self.event_log.log_evaluation(score, total)
        return total

    def score_action(
        self,
        action_type: str,
        success: bool,
        risk_level: float = 0.0,
    ) -> float:
        """动作评分

        Args:
            action_type: explore/exploit/stabilize
            success: 是否成功
            risk_level: 风险级别

        Returns:
            Constitution 加权总分
        """
        score = self.evaluator.evaluate_action(action_type, success, risk_level)
        total = self.vector.score(score.scores)
        self.event_log.log_action_score(action_type, score, total)
        self.logger.info(
            f"[ConstitutionRuntime] score_action: {action_type} "
            f"success={success} → {total:.4f}"
        )
        return total

    def score_goal(
        self,
        goal_type: str,
        goal_achievement: float = 1.0,
    ) -> float:
        """目标评分

        Args:
            goal_type: explore/exploit/stabilize
            goal_achievement: 目标达成度

        Returns:
            Constitution 加权总分
        """
        score = self.evaluator.evaluate_goal(goal_type, goal_achievement)
        total = self.vector.score(score.scores)
        self.event_log.log_goal_score(goal_type, score, total)
        self.logger.info(
            f"[ConstitutionRuntime] score_goal: {goal_type} "
            f"achievement={goal_achievement:.2f} → {total:.4f}"
        )
        return total

    def score_pattern(
        self,
        pattern_fitness: float,
        activation_count: int,
        success_rate: float,
    ) -> float:
        """模式评分

        Args:
            pattern_fitness: Pattern fitness [0,1]
            activation_count: 激活次数
            success_rate: 成功率

        Returns:
            Constitution 加权总分
        """
        score = self.evaluator.evaluate_pattern(
            pattern_fitness, activation_count, success_rate
        )
        total = self.vector.score(score.scores)
        self.event_log.log_pattern_score(score, total)
        self.logger.info(
            f"[ConstitutionRuntime] score_pattern: "
            f"fitness={pattern_fitness:.2f}, rate={success_rate:.2f} → {total:.4f}"
        )
        return total

    def get_vector(self) -> ConstitutionVector:
        """获取当前 Constitution Vector"""
        return self.vector

    def update_weight(self, dimension: str, weight: float) -> None:
        """更新维度权重"""
        old = self.vector.get_weight(dimension)
        self.vector.set_weight(dimension, weight)
        self.event_log.log_weight_update(dimension, old, weight)
        self.logger.info(
            f"[ConstitutionRuntime] weight updated: {dimension} {old:.4f} → {weight:.4f}"
        )

    def get_event_log(self) -> ConstitutionEventLog:
        """获取事件日志"""
        return self.event_log
