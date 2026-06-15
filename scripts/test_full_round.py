import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

import time

print("Testing full teaching round...")
from core.cognition.cognitive_trainer import get_cognitive_trainer
from core.cognition.teaching.question_bank import Question, TeachingTopic

trainer = get_cognitive_trainer()
ts = trainer._get_teaching_system()

q = Question(id='test_001', question='如何设计一个简单的缓存系统�?, topic=TeachingTopic.SELF_AWARENESS, expected_keywords=[])

start = time.time()
print("Starting teaching round...")
try:
    result = ts.run_teaching_round(question=q)
    elapsed = time.time() - start
    print(f"Teaching round completed in {elapsed:.1f}s")
    eval_data = result.get('evaluation', {})
    score = eval_data.get('score', 'N/A')
    feedback = str(eval_data.get('feedback', ''))[:200]
    print(f"Score: {score}")
    print(f"Feedback: {feedback}")
    
    exploration = result.get('exploration_result')
    if exploration:
        print(f"Exploration: improved={exploration.get('improved')}, best_score={exploration.get('best_score')}")
    else:
        print("No exploration")
except Exception as e:
    elapsed = time.time() - start
    print(f"FAILED after {elapsed:.1f}s: {e}")
    import traceback
    traceback.print_exc()
