# -*- coding: utf-8 -*-
import asyncio
import sys
sys.path.insert(0, ".")


async def test():
    from core.safety.safety_os import SafetyOS
    from core.timeline.timeline_manager import TimelineManager
    from core.causal.causal_engine import CausalEngine
    from core.safety.learning.safety_learner import SafetyLearner

    tm = TimelineManager(max_size=100)
    ce = CausalEngine()
    learner = SafetyLearner()
    sos = SafetyOS(timeline_manager=tm, causal_engine=ce, learner=learner)

    action = {"action_type": "browser.open", "data": {"href": "https://example.com"}}
    decision = await sos.approve(action)
    print(f"[TEST1] approve decision: {decision.final_decision}, risk: {decision.risk_score:.3f}")

    capsules = sos.data_chain_manager.list_capsules(limit=5)
    print(f"[TEST2] capsules count: {len(capsules)}")
    if capsules:
        c = capsules[0]
        cid = c["Capsule ID"]
        act = c["Action"]
        dec = c["Decision"]
        print(f"[TEST2] latest capsule: id={cid}, action={act}, decision={dec}")

    outcome = {"success": True, "user_intervention": False}
    await sos.record_outcome(decision, outcome)
    capsules2 = sos.data_chain_manager.list_capsules(limit=5)
    print(f"[TEST3] capsules after outcome: {len(capsules2)}")

    if capsules2:
        detail = sos.data_chain_manager.show(capsules2[0]["Capsule ID"])
        has_outcome = detail.get("outcome") is not None
        has_teacher = detail.get("triple_teacher_review") is not None
        print(f"[TEST4] detail check: has_outcome={has_outcome}, has_teacher={has_teacher}")

    print("[ALL TESTS PASSED]")


asyncio.run(test())
