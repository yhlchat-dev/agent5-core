# -*- coding: utf-8 -*-
import json
import sys
sys.path.insert(0, ".")

from core.cognition.cognitive_kernel_v2 import CognitiveKernelV2
from core.cognition.hypothesis_engine import HypothesisEngine
from core.cognition.attention_unified import AttentionUnified

print("=" * 90)
print("小七 统一认知流系�?测试")
print("=" * 90)

he = HypothesisEngine()
at = AttentionUnified()

print("\n【测�?】HypothesisEngine - 高风险操�?)
h1 = he.generate({"risk": 0.8, "intent": "delete", "raw_input": "删除核心文件"})
print(f"  hypotheses: {h1}")

print("\n【测�?】HypothesisEngine - 低风险操�?)
h2 = he.generate({"risk": 0.1, "intent": "read", "raw_input": "查询用户信息"})
print(f"  hypotheses: {h2}")

print("\n【测�?】HypothesisEngine - 未知操作")
h3 = he.generate({"raw_input": "你好"})
print(f"  hypotheses: {h3}")

print("\n【测�?】AttentionUnified - 高风�?低奖�?)
a1 = at.score({"risk": 0.8, "reward": -1.0, "uncertain": True, "novelty": 0.6})
print(f"  attention_score: {a1}")

print("\n【测�?】AttentionUnified - 低风�?高奖�?)
a2 = at.score({"risk": 0.1, "reward": 1.0, "uncertain": False, "novelty": 0.1})
print(f"  attention_score: {a2}")

print("\n【测�?】CognitiveKernelV2 - 完整认知�?)
kernel = CognitiveKernelV2()
result = kernel.infer({
    "type": "action_request",
    "task": "删除核心文件",
    "action": "file_delete",
    "risk": 0.8,
    "raw_input": "删除核心文件"
})
print(f"  action: {result.get('action')}")
print(f"  approved: {result.get('approved')}")
print(f"  confidence: {result.get('confidence'):.3f}")
print(f"  attention_score: {result.get('attention_score')}")
print(f"  hypotheses_in_state: {'hypotheses' in str(result)}")

print("\n【测�?】CognitiveKernelV2 - 低风险操�?)
result2 = kernel.infer({
    "type": "action_request",
    "task": "查询用户信息",
    "action": "read_data",
    "risk": 0.1,
    "raw_input": "查询用户信息"
})
print(f"  action: {result2.get('action')}")
print(f"  attention_score: {result2.get('attention_score')}")

print("\n" + "=" * 90)
print("�?统一认知流系统测试完成！")
print("认知流：Hypothesis �?Memory �?Decision �?Attention �?Observation")
print("=" * 90)
