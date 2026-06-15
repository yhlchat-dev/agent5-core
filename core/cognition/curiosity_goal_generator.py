# -*- coding: utf-8 -*-
"""
CuriosityGoalGenerator — Curiosity V3 Goal Generation 模块

Phase 7.6 新增：基于好奇心信号自动生成目标

规则：
- curiosity_score > 0.7 → generate_exploratory_goal (type: explore)
- curiosity_score > 0.4 → generate_incremental_goal (type: exploit)
- curiosity_score <= 0.4 → no new goal (type: stabilize)

输出结构：
{
    "goal": string,
    "type": "explore | exploit | stabilize",
    "source": "curiosity_v3"
}
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import time


@dataclass
class CuriosityGoal:
    """好奇心驱动的目标"""
    goal: str
    type: str          # explore / exploit / stabilize
    source: str = "curiosity_v3"
    curiosity_score: float = 0.0
    gap_total: float = 0.0
    topic: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "type": self.type,
            "source": self.source,
            "curiosity_score": self.curiosity_score,
            "gap_total": self.gap_total,
            "topic": self.topic,
        }


# 探索目标模板
EXPLORE_GOAL_TEMPLATES = [
    "探索 {topic} 的未知领域",
    "调查 {topic} 的异常模式",
    "发现 {topic} 的新关联",
    "验证 {topic} 的假设",
]

EXPLOIT_GOAL_TEMPLATES = [
    "优化 {topic} 的当前策略",
    "改进 {topic} 的执行效率",
    "巩固 {topic} 的已有知识",
    "微调 {topic} 的参数",
]

STABILIZE_GOAL = "维持当前状态，观察系统变化"


class CuriosityGoalGenerator:
    """好奇心目标生成器

    根据 curiosity_score 和 gap_vector 自动生成目标，
    无需外部输入即可产生 explore/exploit/stabilize 类型目标。

    Phase 8.4 接线 D: PolicyVector 影响 Goal System
    - exploration_pressure > threshold → 提高 CuriosityWeight
    - suppression_ratio > threshold → 降低 GoalPersistence
    """

    def __init__(self) -> None:
        self._generated_goals: List[CuriosityGoal] = []
        # Phase 8.4: 可被 PolicyVector 覆盖
        self.curiosity_weight: float = 1.0
        self.goal_persistence: float = 1.0

    def inject_policy(self, policy, suppression_ratio: float = 0.0) -> None:
        """Phase 8.4: 从 PolicyVector 注入参数

        - gene_amplification_factor 高 → exploration_pressure 高 → 提高 CuriosityWeight
        - suppression_ratio 高 → 降低 GoalPersistence
        """
        # exploration_pressure 从 amplification_factor 推导
        exploration_pressure = policy.gene_amplification_factor - 1.0  # 0.0~1.0
        if exploration_pressure > 0.3:
            self.curiosity_weight = 1.0 + exploration_pressure * 0.5  # 1.0~1.5
        else:
            self.curiosity_weight = 1.0

        if suppression_ratio > 0.5:
            self.goal_persistence = max(0.3, 1.0 - suppression_ratio * 0.8)
        else:
            self.goal_persistence = 1.0

    def generate_goal(
        self,
        curiosity_score: float,
        gap_total: float = 0.0,
        topic: str = "",
        reward_score: float = 0.0,
        stability_metrics: Optional[Dict[str, float]] = None,
    ) -> Optional[CuriosityGoal]:
        """根据好奇心信号生成目标

        Phase 7.6 P2: 新增仲裁逻辑
        - stability < 0.3 → prioritize_stability_goal
        - curiosity_score > reward_score → prioritize_exploration_goal
        - else → prioritize_reward_goal (exploit)

        Args:
            curiosity_score: 当前好奇心分数 [0, 1]（已被 reward_pressure 压制后的值）
            gap_total: 差距综合值
            topic: 当前关注的主题
            reward_score: 当前 reward 分数 [0, 1]
            stability_metrics: 稳定性指标（含 instability 等）

        Returns:
            CuriosityGoal
        """
        metrics = stability_metrics or {}

        # Phase 8.4: curiosity_weight 放大好奇心信号
        weighted_curiosity = curiosity_score * self.curiosity_weight

        # Phase 7.6 P2: 仲裁逻辑
        instability = metrics.get("instability", 0.0)
        stability = 1.0 - instability

        if stability < 0.3 * self.goal_persistence:
            return self._generate_stabilize_goal(weighted_curiosity, gap_total)
        elif weighted_curiosity > reward_score:
            return self._generate_exploratory_goal(weighted_curiosity, gap_total, topic)
        else:
            return self._generate_incremental_goal(weighted_curiosity, gap_total, topic)

    def _generate_exploratory_goal(
        self, curiosity_score: float, gap_total: float, topic: str,
    ) -> CuriosityGoal:
        """生成探索型目标"""
        import random
        template = random.choice(EXPLORE_GOAL_TEMPLATES)
        goal_text = template.format(topic=topic or "系统状态")
        goal = CuriosityGoal(
            goal=goal_text,
            type="explore",
            curiosity_score=curiosity_score,
            gap_total=gap_total,
            topic=topic,
        )
        self._generated_goals.append(goal)
        return goal

    def _generate_incremental_goal(
        self, curiosity_score: float, gap_total: float, topic: str,
    ) -> CuriosityGoal:
        """生成增量型目标"""
        import random
        template = random.choice(EXPLOIT_GOAL_TEMPLATES)
        goal_text = template.format(topic=topic or "当前策略")
        goal = CuriosityGoal(
            goal=goal_text,
            type="exploit",
            curiosity_score=curiosity_score,
            gap_total=gap_total,
            topic=topic,
        )
        self._generated_goals.append(goal)
        return goal

    def _generate_stabilize_goal(
        self, curiosity_score: float, gap_total: float,
    ) -> CuriosityGoal:
        """生成稳定型目标（低好奇心时维持现状）"""
        goal = CuriosityGoal(
            goal=STABILIZE_GOAL,
            type="stabilize",
            curiosity_score=curiosity_score,
            gap_total=gap_total,
        )
        self._generated_goals.append(goal)
        return goal

    @property
    def goal_count(self) -> int:
        return len(self._generated_goals)

    def recent_goals(self, n: int = 10) -> List[CuriosityGoal]:
        return self._generated_goals[-n:]

    def get_stats(self) -> Dict[str, Any]:
        explore_count = sum(1 for g in self._generated_goals if g.type == "explore")
        exploit_count = sum(1 for g in self._generated_goals if g.type == "exploit")
        stabilize_count = sum(1 for g in self._generated_goals if g.type == "stabilize")
        return {
            "total_goals": len(self._generated_goals),
            "explore": explore_count,
            "exploit": exploit_count,
            "stabilize": stabilize_count,
        }
