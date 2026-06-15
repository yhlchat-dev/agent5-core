import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

import time

print("Step 1: Testing LLMBridge directly...")
from core.perception.interpreter.llm_bridge import LLMBridge

llm = LLMBridge()
if not llm.initialize():
    print("LLMBridge init FAILED")
    sys.exit(1)

start = time.time()
result = llm.call(
    prompt="请回答：如何设计一个简单的缓存系统�?,
    system_prompt="你是Agent 5.0",
    max_tokens=500,
    temperature=0.7,
    skip_identity_check=True
)
elapsed = time.time() - start
print(f"LLMBridge call took {elapsed:.1f}s")
print(f"Result: {result[:200] if result else 'None'}")

print("\nStep 2: Testing student answer generation...")
from core.cognition.cognitive_trainer import get_cognitive_trainer
from core.cognition.teaching.question_bank import Question, TeachingTopic

trainer = get_cognitive_trainer()
ts = trainer._get_teaching_system()

q = Question(id='test_001', question='如何设计一个简单的缓存系统�?, topic=TeachingTopic.SELF_AWARENESS, expected_keywords=[])

start = time.time()
answer = ts._generate_student_answer(q)
elapsed = time.time() - start
print(f"Student answer took {elapsed:.1f}s")
print(f"Answer: {answer[:200]}")

print("\nStep 3: Testing dual teacher evaluation...")
from core.cognition.teaching.teacher_model import get_teacher_model, TeacherType
teacher = get_teacher_model()

start = time.time()
dual_result = teacher.teach_with_dual_teachers_sync(
    question=q.question,
    student_answer=answer,
    topic="skill_generation"
)
elapsed = time.time() - start
print(f"Dual teacher took {elapsed:.1f}s")
print(f"Final score: {dual_result.final_score}")
print(f"Volcano: {dual_result.volcano_score}, DeepSeek: {dual_result.deepseek_score}")

print("\nAll steps completed!")
