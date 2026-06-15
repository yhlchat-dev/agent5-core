# -*- coding: utf-8 -*-


from typing import Any, Dict, Optional
class CausalJudge:

    def __init__(self, llm: Optional[Any] = None) -> None:
        self.llm = llm

    def evaluate(self, state_action: str, outcome) -> Dict[str, Any]:
        if self.llm:
            prompt = f"""
            分析该行为是否解决根本原因：

            状态: {state_action['state']}
            动作: {state_action['action']}
            结果: {outcome}

            输出：
            1. 是否解决根因（-1~1）
            2. 因果置信度（0~1）
            """

            resp = self.llm(prompt)

            return {
                "causal_score": resp.get("root_cause_score", 0.0),
                "confidence": resp.get("confidence", 0.5)
            }

        causal_score = 0.5
        if outcome == "success":
            causal_score = 0.8
        elif outcome == "fail":
            causal_score = -0.3

        return {
            "causal_score": causal_score,
            "confidence": 0.5
        }
