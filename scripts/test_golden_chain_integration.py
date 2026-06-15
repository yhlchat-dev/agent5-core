# -*- coding: utf-8 -*-
import asyncio
import json
import sys
sys.path.insert(0, ".")

from core.safety.safety_os import SafetyOS
from core.timeline.timeline_manager import TimelineManager
from core.causal.causal_engine import CausalEngine
from core.safety.learning.safety_learner import SafetyLearner
from core.memory_system.capsules.golden_data_chain_capsule import GoldenDataChainManager
from datetime import datetime

print("=" * 90)
print("小七 黄金数据链主流程集成测试（execute_with_golden_chain�?)
print("=" * 90)


class MockApp:
    """模拟 AgentApplication 的最小子�?""

    def __init__(self):
        from core.utils.logger import get_logger
        self.logger = get_logger("test.mock_app")

        from core.cognition.identity_core import get_identity_core
        self.identity_core = get_identity_core()

        tm = TimelineManager(max_size=1000)
        ce = CausalEngine()
        learner = SafetyLearner()
        self.safety_os = SafetyOS(timeline_manager=tm, causal_engine=ce, learner=learner)

        self.golden_chain_manager = GoldenDataChainManager()
        self.curiosity_system = None

    async def execute_with_golden_chain(self, action_context: dict, execute_fn=None):
        from datetime import datetime as _dt

        perception = {
            "source": action_context.get("source", "user_or_env"),
            "timestamp": _dt.now().isoformat(),
            "raw_input": action_context.get("raw_input", str(action_context)[:200])
        }

        decision = await self.safety_os.approve(action_context)

        cognition = {
            "identity_state": getattr(self.identity_core, "current_state", None),
            "value_alignment": None,
            "curiosity_score": getattr(self.curiosity_system, "total_score", None) if self.curiosity_system else None
        }

        outcome = None
        if execute_fn and decision.final_decision == "allow":
            try:
                result = await execute_fn(action_context)
                outcome = {"success": True, "result": result, "user_intervention": False}
            except Exception as e:
                outcome = {"success": False, "error": str(e), "user_intervention": False}
            await self.safety_os.record_outcome(decision, outcome)

        memory_storage = {"stored_in": ["episodic", "semantic"], "capsule_ids": []}

        safety_audit = {
            "decision": decision.to_dict() if hasattr(decision, "to_dict") else {"risk_score": decision.risk_score, "final_decision": decision.final_decision},
            "triple_teacher": getattr(decision, "triple_teacher_review", {})
        }

        behavior_output = {
            "executed_action": action_context.get("action_type", "unknown"),
            "decision": decision.final_decision,
            "outcome": outcome
        }

        learning_reward = 0.0
        if hasattr(self.safety_os, "learner") and self.safety_os.learner:
            try:
                learning_reward = self.safety_os.learner._calc_reward(
                    decision, outcome or {}, getattr(decision, "triple_teacher_review", None)
                )
            except Exception:
                pass

        drift_info = self.safety_os.check_drift() if hasattr(self.safety_os, "check_drift") else {}

        self_growth = {
            "learning_reward": learning_reward,
            "drift_score": drift_info.get("drift_score", 0.0),
            "drift_detected": drift_info.get("drift", False)
        }

        golden_chain = self.golden_chain_manager.create_chain(
            perception=perception,
            cognition=cognition,
            memory_storage=memory_storage,
            safety_audit=safety_audit,
            behavior_output=behavior_output,
            self_growth=self_growth
        )

        self.logger.info(f"[小七] 黄金数据链已生成: {golden_chain.capsule_id}, trace={golden_chain.traceability_id}")
        return golden_chain


async def run_test():
    app = MockApp()

    print("\n【测�?】低风险动作 + 黄金数据�?)
    chain1 = await app.execute_with_golden_chain(
        {"action_type": "read_data", "content": "查询用户信息", "source": "user_input"}
    )
    print(f"�?capsule_id: {chain1.capsule_id}")
    print(f"�?trace_id: {chain1.traceability_id}")
    print(f"�?perception: {chain1.perception}")
    print(f"�?safety decision: {chain1.safety_audit.get('decision', {}).get('final_decision')}")

    print("\n【测�?】高风险动作 + 黄金数据�?)
    chain2 = await app.execute_with_golden_chain(
        {"action_type": "file_delete", "path": "/core/secret.py", "source": "user_input"}
    )
    print(f"�?capsule_id: {chain2.capsule_id}")
    print(f"�?safety decision: {chain2.safety_audit.get('decision', {}).get('final_decision')}")
    print(f"�?self_growth: {chain2.self_growth}")

    print("\n【测�?】带执行函数的黄金数据链")
    async def mock_execute(ctx):
        return {"status": "done", "data": "result_data"}

    chain3 = await app.execute_with_golden_chain(
        {"action_type": "browser.open", "data": {"href": "https://example.com"}, "source": "env"},
        execute_fn=mock_execute
    )
    print(f"�?behavior_output: {chain3.behavior_output}")

    print("\n【测�?】查看黄金数据链列表")
    table = app.golden_chain_manager.list_chains(limit=5)
    for row in table:
        print(row)

    print("\n【测�?】验证全链路6阶段完整�?)
    detail = app.golden_chain_manager.show(chain1.capsule_id)
    stages = ["perception", "cognition", "memory_storage", "safety_audit", "behavior_output", "self_growth"]
    all_ok = True
    for stage in stages:
        has_data = detail.get(stage) is not None
        status = "�? if has_data else "�?
        print(f"  {stage}: {status}")
        if not has_data:
            all_ok = False

    print("\n" + "=" * 90)
    if all_ok:
        print("�?所有黄金数据链主流程集成测试完成！")
    else:
        print("�?部分阶段缺失数据")
    print(f"黄金数据链目�? {app.golden_chain_manager.base_dir}")
    print("=" * 90)


asyncio.run(run_test())
