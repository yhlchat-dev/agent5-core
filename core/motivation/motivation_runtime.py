# -*- coding: utf-8 -*-
"""
MotivationRuntime — 动机运行时统一接口

向 Goal / Planner / Pattern Learning / Constitution 提供动机信息。
"""
import logging
from typing import Optional

from core.motivation.motivation_state import MotivationState
from core.motivation.motivation_engine import MotivationEngine
from core.motivation.intrinsic_reward_engine import IntrinsicRewardEngine


class MotivationRuntime:
    """动机运行时 — 统一接口

    提供：
    - get_motivation(): 获取当前 MotivationState
    - update_motivation(): 根据事件更新状态
    - score_goal(): 评估目标的内在奖励
    - score_exploration(): 评估探索行为
    - score_persistence(): 评估持久行为
    """

    def __init__(
        self,
        engine: Optional[MotivationEngine] = None,
        intrinsic_engine: Optional[IntrinsicRewardEngine] = None,
    ):
        self.engine = engine or MotivationEngine()
        self.intrinsic_engine = intrinsic_engine or IntrinsicRewardEngine()
        self.logger = logging.getLogger("MotivationRuntime")

    def get_motivation(self) -> MotivationState:
        """获取当前 MotivationState"""
        return self.engine.get_state()

    def update_motivation(self, event: str, magnitude: float = 1.0) -> MotivationState:
        """根据事件更新动机状态

        Args:
            event: success / failure / novelty / long_term_goal
            magnitude: 事件强度
        """
        if event == "success":
            return self.engine.on_success(magnitude)
        elif event == "failure":
            return self.engine.on_failure(magnitude)
        elif event == "novelty":
            return self.engine.on_novelty(magnitude)
        elif event == "long_term_goal":
            return self.engine.on_long_term_goal(magnitude)
        else:
            self.logger.warning(f"[MotivationRuntime] unknown event: {event}")
            return self.engine.get_state()

    def score_goal(self, goal_type: str) -> float:
        """评估目标的内在奖励"""
        state = self.engine.get_state()
        return self.intrinsic_engine.score_goal(state, goal_type)

    def score_exploration(self) -> float:
        """评估探索行为的内在奖励"""
        state = self.engine.get_state()
        return self.intrinsic_engine.score_exploration(state)

    def score_persistence(self) -> float:
        """评估持久行为的内在奖励"""
        state = self.engine.get_state()
        return self.intrinsic_engine.score_persistence(state)

    def compute_intrinsic_reward(self, is_novel: bool = False, mastery_level: float = 0.5) -> float:
        """计算综合内在奖励"""
        state = self.engine.get_state()
        return self.intrinsic_engine.compute(state, is_novel, mastery_level)

    def tick(self) -> MotivationState:
        """每个 cycle 的自然衰减"""
        return self.engine.tick()
