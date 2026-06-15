# -*- coding: utf-8 -*-
from core.safety.audit.models import RiskResult


from typing import Any, Dict
class RiskEvaluator:

    # [枚举值] - 无需迁移
    HIGH_RISK_KEYWORDS = ["delete", "remove", "drop", "format", "wipe"]
    # [枚举值] - 无需迁移
    MEDIUM_RISK_KEYWORDS = ["write", "modify", "update", "create", "install"]

    def evaluate(self, action: str, params: Dict[str, Any]) -> str:
        params_str = str(params).lower()

        for kw in self.HIGH_RISK_KEYWORDS:
            if kw in params_str:
                return "high"

        for kw in self.MEDIUM_RISK_KEYWORDS:
            if kw in params_str:
                return "medium"

        return "low"

    def evaluate_risk(self, action_context: str) -> RiskResult:
        action_type = action_context.get("action_type", "") if isinstance(action_context, dict) else str(action_context)
        params_str = str(action_context).lower()
        confidence = 0.5

        for kw in self.HIGH_RISK_KEYWORDS:
            if kw in params_str:
                confidence = 0.9
                return RiskResult(
                    risk_score=0.8,
                    confidence=confidence,
                    risk_level="high",
                    details={"matched_keyword": kw, "action_type": action_type}
                )

        for kw in self.MEDIUM_RISK_KEYWORDS:
            if kw in params_str:
                confidence = 0.7
                return RiskResult(
                    risk_score=0.6,
                    confidence=confidence,
                    risk_level="medium",
                    details={"matched_keyword": kw, "action_type": action_type}
                )

        return RiskResult(
            risk_score=0.1,
            confidence=0.6,
            risk_level="low",
            details={"action_type": action_type}
        )
