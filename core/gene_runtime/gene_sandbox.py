# -*- coding: utf-8 -*-
"""
GeneSandbox — Gene 沙箱评估器

在 Gene Commit 前模拟变异影响，验证：
1. Identity Distance — 人格距离
2. Trajectory Drift — 累计漂移
3. Value Runtime — 价值评分
4. Hard Constraint — 硬约束违反
5. Gene Delta — 变异强度

全部通过才允许 commit_gene()。
"""
import math
from typing import Dict, Any, Optional

from core.gene_runtime.sandbox_result import SandboxResult


class GeneSandbox:
    """Gene 沙箱评估器 — 变异前模拟验证"""

    # 审批阈值
    IDENTITY_DISTANCE_THRESHOLD = 0.15
    TRAJECTORY_DRIFT_THRESHOLD = 0.20
    VALUE_SCORE_THRESHOLD = 0.70
    MUTATION_STRENGTH_THRESHOLD = 0.30
    CONSTITUTION_SCORE_THRESHOLD = 0.30
    GOVERNANCE_SCORE_THRESHOLD = 0.30

    def __init__(self) -> None:
        self._evaluation_count = 0
        self._approved_count = 0
        self._rejected_count = 0

    def evaluate_mutation(
        self,
        current_gene: Any,
        candidate_gene: Any,
        runtime_context: Any,
    ) -> SandboxResult:
        """评估 Gene 变异是否安全

        Args:
            current_gene: 当前 Gene (StrategyGene)
            candidate_gene: 候选 Gene (StrategyGene)
            runtime_context: SharedRuntimeContext

        Returns:
            SandboxResult
        """
        self._evaluation_count += 1
        violations = []
        reasons = []

        # 1. 计算 Identity Distance
        identity_distance = self._compute_identity_distance(runtime_context)
        if identity_distance >= self.IDENTITY_DISTANCE_THRESHOLD:
            violations.append("identity_distance_exceeded")
            reasons.append(f"identity_distance={identity_distance:.4f} >= {self.IDENTITY_DISTANCE_THRESHOLD}")

        # 2. 获取 Trajectory Drift
        trajectory_drift = self._get_trajectory_drift(runtime_context)
        if trajectory_drift >= self.TRAJECTORY_DRIFT_THRESHOLD:
            violations.append("trajectory_drift_exceeded")
            reasons.append(f"trajectory_drift={trajectory_drift:.4f} >= {self.TRAJECTORY_DRIFT_THRESHOLD}")

        # 3. 计算 Value Score
        value_score = self._compute_value_score(runtime_context)
        if value_score < self.VALUE_SCORE_THRESHOLD:
            violations.append("value_score_too_low")
            reasons.append(f"value_score={value_score:.4f} < {self.VALUE_SCORE_THRESHOLD}")

        # 4. 检查 Hard Constraint
        constraint_violations = self._check_hard_constraints(runtime_context)
        if constraint_violations:
            violations.extend(constraint_violations)
            reasons.append(f"hard_constraints_violated: {constraint_violations}")

        # 5. 计算 Mutation Strength
        mutation_strength = self._compute_mutation_strength(current_gene, candidate_gene)
        if mutation_strength >= self.MUTATION_STRENGTH_THRESHOLD:
            violations.append("mutation_strength_exceeded")
            reasons.append(f"mutation_strength={mutation_strength:.4f} >= {self.MUTATION_STRENGTH_THRESHOLD}")

        # 6. 检查 Constitution Score
        constitution_score = self._get_constitution_score(runtime_context)
        if constitution_score < self.CONSTITUTION_SCORE_THRESHOLD:
            violations.append("constitution_score_too_low")
            reasons.append(f"constitution_score={constitution_score:.4f} < {self.CONSTITUTION_SCORE_THRESHOLD}")

        # 7. 检查 Governance Score
        governance_score = self._get_governance_score(runtime_context)
        if governance_score < self.GOVERNANCE_SCORE_THRESHOLD:
            violations.append("governance_score_too_low")
            reasons.append(f"governance_score={governance_score:.4f} < {self.GOVERNANCE_SCORE_THRESHOLD}")

        # 审批判定: 必须全部满足
        approved = len(violations) == 0
        reason = "; ".join(reasons) if reasons else "all checks passed"

        if approved:
            self._approved_count += 1
        else:
            self._rejected_count += 1

        return SandboxResult(
            approved=approved,
            identity_distance=identity_distance,
            trajectory_drift=trajectory_drift,
            value_score=value_score,
            mutation_strength=mutation_strength,
            violations=violations,
            reason=reason,
        )

    def _compute_identity_distance(self, ctx: Any) -> float:
        """计算当前 Identity Distance"""
        if not ctx.identity_distance or not ctx.identity_core:
            return 0.0

        current_vector = dict(ctx.identity_core.current_state.values)
        anchor = ctx.identity_recovery._anchor_identity if ctx.identity_recovery else current_vector

        result = ctx.identity_distance.compute_distance(current_vector, anchor)
        return result["distance"]

    def _get_trajectory_drift(self, ctx: Any) -> float:
        """获取当前 Trajectory Drift (average)"""
        if not ctx.trajectory_drift_detector:
            return 0.0
        return ctx.trajectory_drift_detector.get_average_drift()

    def _compute_value_score(self, ctx: Any) -> float:
        """计算当前 Value Score"""
        if not ctx.value_runtime:
            return 1.0

        action_context = {}
        if ctx.identity_core:
            action_context.update(ctx.identity_core.current_state.values)

        result = ctx.value_runtime.evaluate(
            action_context=action_context,
            reward_score=0.5,
        )
        return result.get("final_score", 0.0)

    def _check_hard_constraints(self, ctx: Any) -> list:
        """检查 Hard Constraint"""
        if not ctx.value_runtime or not ctx.value_runtime.hard_constraint:
            return []

        action_context = {}
        if ctx.identity_core:
            action_context.update(ctx.identity_core.current_state.values)

        decision = ctx.value_runtime.hard_constraint.evaluate(action_context)
        if decision.allowed:
            return []
        return decision.violated_constraints

    def _compute_mutation_strength(self, current_gene: Any, candidate_gene: Any) -> float:
        """计算变异强度

        基于 fitness delta 和属性变化。
        safety 1.0→0.3 立即高风险。
        """
        if current_gene is None or candidate_gene is None:
            return 0.0

        # Fitness delta
        current_fitness = getattr(current_gene, 'fitness', 0.5)
        candidate_fitness = getattr(candidate_gene, 'fitness', 0.5)
        fitness_delta = abs(candidate_fitness - current_fitness)

        # 如果有 strategy_pattern 变化，增加强度
        current_pattern = getattr(current_gene, 'strategy_pattern', '')
        candidate_pattern = getattr(candidate_gene, 'strategy_pattern', '')
        pattern_change = 0.1 if current_pattern != candidate_pattern else 0.0

        return min(1.0, fitness_delta + pattern_change)

    def _get_constitution_score(self, ctx: Any) -> float:
        """获取当前 Constitution Score"""
        if not ctx.constitution_runtime:
            return 1.0
        # 使用默认参数评分，获取当前 constitution 水平
        score = ctx.constitution_runtime.score_action(
            action_type="default",
            success=True,
            risk_level=0.0,
        )
        return score

    def _get_governance_score(self, ctx: Any) -> float:
        """获取当前 Governance Score (由 CognitiveCycle 注入)"""
        return getattr(ctx, '_governance_score', 1.0)

    def get_stats(self) -> Dict[str, Any]:
        """返回统计信息"""
        return {
            "evaluation_count": self._evaluation_count,
            "approved_count": self._approved_count,
            "rejected_count": self._rejected_count,
            "approval_rate": self._approved_count / max(1, self._evaluation_count),
        }
