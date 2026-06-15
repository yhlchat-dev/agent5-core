# -*- coding: utf-8 -*-
from typing import Dict, Any, Optional, List


class RewardExplainer:
    """奖励解释器 - 把数字变成可学习的原因链

    核心职责：
    1. 计算奖励值（与 SafetyLearner._calc_reward 一致）
    2. 生成人类/模型可读的奖励归因（为什么是这个分数）
    3. 输出可直接用于 LLM 训练的结构化解释
    """

    def explain(self,
                decision: Dict[str, Any],
                teacher: Dict[str, Any],
                outcome: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        factors = []
        reward = 0.0
        success = (outcome or {}).get("success", False)
        reward, factors = self._outcome_factor(success, reward, factors)
        expected = (teacher or {}).get("recommendation", "allow").lower()
        actual = (decision or {}).get("final_decision", "unknown").lower()
        fusion = (teacher or {}).get("fusion_score", 0.0)
        reward, factors = self._teacher_alignment_factor(expected, actual, fusion, reward, factors)
        user_intervention = (outcome or {}).get("user_intervention", False)
        reward, factors = self._user_intervention_factor(user_intervention, reward, factors)
        reward = max(min(reward, 1.0), -1.0)
        alignment = self._determine_alignment(expected, actual, success, user_intervention)
        reason = self._build_reason(factors, alignment)
        trainable_signal = {
            "reward": reward, "alignment": alignment,
            "key_factors": [f["name"] for f in factors],
            "teacher_expected": expected, "actual_decision": actual,
            "outcome_success": success, "user_intervention": user_intervention,
        }
        return {"reward": reward, "factors": factors, "reason": reason, "alignment": alignment, "trainable_signal": trainable_signal}

    def _outcome_factor(self, success: bool, reward: float, factors: list):
        if success:
            reward += 1.0
            factors.append({"name": "outcome_success", "contribution": 1.0, "desc": "执行成功"})
        else:
            reward -= 0.8
            factors.append({"name": "outcome_failure", "contribution": -0.8, "desc": "执行失败"})
        return reward, factors

    def _teacher_alignment_factor(self, expected: str, actual: str, fusion: float, reward: float, factors: list):
        if expected and actual and expected == actual:
            bonus = 0.7 * fusion
            reward += bonus
            factors.append({"name": "teacher_aligned", "contribution": bonus, "desc": f"决策与三老师一致 (recommendation={expected}, fusion={fusion:.2f})"})
        elif expected and actual:
            reward -= 0.5
            factors.append({"name": "teacher_deviation", "contribution": -0.5, "desc": f"决策偏离三老师 (expected={expected}, actual={actual})"})
        return reward, factors

    def _user_intervention_factor(self, user_intervention: bool, reward: float, factors: list):
        if user_intervention:
            reward -= 0.6
            factors.append({"name": "user_intervention", "contribution": -0.6, "desc": "用户手动干预（决策可能不当）"})
        return reward, factors

    def _determine_alignment(self, expected: str, actual: str,
                             success: bool, user_intervention: bool) -> str:
        if user_intervention:
            return "misaligned_user_corrected"
        if expected == actual and success:
            return "fully_aligned"
        if expected == actual and not success:
            return "aligned_but_failed"
        if expected != actual:
            return "deviated_from_teacher"
        return "unknown"

    def _build_reason(self, factors: List[Dict], alignment: str) -> str:
        parts = []
        for f in factors:
            sign = "+" if f["contribution"] >= 0 else ""
            parts.append(f"{f['desc']} ({sign}{f['contribution']:.1f})")

        reason_body = "; ".join(parts)

        alignment_map = {
            "fully_aligned": "完全对齐",
            "aligned_but_failed": "对齐但执行失败",
            "deviated_from_teacher": "偏离三老师建议",
            "misaligned_user_corrected": "用户纠正（决策不当）",
            "unknown": "状态未知"
        }

        return f"[{alignment_map.get(alignment, alignment)}] {reason_body}"
