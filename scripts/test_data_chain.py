# -*- coding: utf-8 -*-
import asyncio
import sys
sys.path.insert(0, '.')

from core.safety.safety_os import SafetyOS
from core.timeline.timeline_manager import TimelineManager
from core.causal.causal_engine import CausalEngine
from core.safety.learning.safety_learner import SafetyLearner


class MockApp:
    def __init__(self):
        tm = TimelineManager(max_size=2000)
        ce = CausalEngine()
        learner = SafetyLearner()
        self.safety_os = SafetyOS(timeline_manager=tm, causal_engine=ce, learner=learner)

    async def print_full_data_chain(self, action_context, decision=None, outcome=None):
        print("\n" + "=" * 100)
        print("小七 完整数据链输�?)
        print("=" * 100)

        print(f"\n�?. 动作请求�?)
        print(f"Action Type : {action_context.get('action_type', 'unknown')}")
        print(f"Details     : {action_context}")

        if decision:
            print(f"\n�?. SafetyOS 决策�?)
            print(f"Risk Score      : {decision.risk_score:.3f}")
            print(f"Final Decision  : {decision.final_decision}")
            print(f"Reason          : {decision.reason}")

            if decision.triple_teacher_review:
                tr = decision.triple_teacher_review
                print(f"\n�?. 三老师审查 (对错�?�?)
                fusion = tr.get('fusion_score', 'N/A')
                if isinstance(fusion, (int, float)):
                    print(f"Fusion Score    : {fusion:.3f}")
                else:
                    print(f"Fusion Score    : {fusion}")
                print(f"Recommendation  : {tr.get('recommendation', 'N/A')}")
                print(f"Summary         : {tr.get('summary', 'N/A')}")

        print(f"\n�?. 时间轴记录�?)
        if hasattr(self, 'safety_os') and self.safety_os:
            events = self.safety_os.timeline.safety(limit=5)
            for e in events[-3:]:
                ts = e.get('ts', '')
                if isinstance(ts, (int, float)):
                    ts = str(ts)
                print(f"  {str(ts)[:19]} | {e.get('type', '')} | {e.get('final_decision', '')}")

        print(f"\n�?. 因果链�?)
        if decision and hasattr(self, 'safety_os') and self.safety_os:
            causal = self.safety_os.timeline.causal(decision.decision_id)
            print(f"Root Causes : {causal.get('causes', [])}")
            print(f"Effects     : {causal.get('effects', [])}")

        print(f"\n�?. 认知OS 对错�?& Identity�?)
        if hasattr(self, 'cognitive_kernel'):
            ck = self.cognitive_kernel
            if hasattr(ck, 'identity_core'):
                print(f"Current Identity : {str(getattr(ck.identity_core, 'current_state', 'N/A'))[:80]}...")

        print(f"\n�?. 学习信号�?)
        print(f"Outcome Success   : {outcome.get('success', '待执�?) if outcome else '待执�?}")
        print(f"User Intervention : {outcome.get('user_intervention', False) if outcome else 'N/A'}")

        print(f"\n�?. 漂移检测�?)
        if hasattr(self, 'safety_os') and self.safety_os:
            drift = self.safety_os.check_drift()
            print(f"漂移状�?: {drift.get('drift', False)}")
            print(f"建议     : {drift.get('recommendation', 'N/A')}")

        print("\n" + "=" * 100)
        print("数据链输出完�?)
        print("=" * 100)


if __name__ == "__main__":
    app = MockApp()
    action = {"action_type": "file_modify", "path": "/core/important.py", "content": "敏感修改"}
    decision = asyncio.run(app.safety_os.approve(action))
    outcome = {"success": True, "user_intervention": False}
    asyncio.run(app.safety_os.record_outcome(decision, outcome))
    asyncio.run(app.print_full_data_chain(action, decision=decision, outcome=outcome))
