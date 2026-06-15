import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

import time

print("Step 1: Generate student answer...")
from core.perception.interpreter.llm_bridge import LLMBridge
from core.memory_system.capsules.agent_self_identity_capsule import get_self_identity_capsule

llm = LLMBridge()
llm.initialize()

capsule = get_self_identity_capsule()
system_prompt = capsule.format_for_system_prompt()
print(f"System prompt length: {len(system_prompt)}")

start = time.time()
answer = llm.call(
    prompt="请回答以下问题：\n\n如何设计一个简单的缓存系统？\n\n请根据你的身份和能力，给出一个准确、完整的回答�?,
    system_prompt=system_prompt,
    max_tokens=500,
    temperature=0.7,
    skip_identity_check=False
)
elapsed = time.time() - start
print(f"Student answer took {elapsed:.1f}s")
print(f"Answer: {answer[:200] if answer else 'None'}")

print("\nStep 2: Dual teacher evaluation...")
from core.cognition.teaching.teacher_model import get_teacher_model, TeacherType
teacher = get_teacher_model()

start = time.time()
dual_result = teacher.teach_with_dual_teachers_sync(
    question="如何设计一个简单的缓存系统�?,
    student_answer=answer or "无法回答",
    topic="skill_generation"
)
elapsed = time.time() - start
print(f"Dual teacher took {elapsed:.1f}s")
print(f"Final score: {dual_result.final_score}")
print(f"Volcano: {dual_result.volcano_score}, DeepSeek: {dual_result.deepseek_score}")

print("\nAll steps completed successfully!")
