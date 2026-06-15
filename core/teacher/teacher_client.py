# -*- coding: utf-8 -*-
from typing import Any, Dict
class TeacherClient:

    def __init__(self, teacher_queue) -> None:
        self.queue = teacher_queue

    def ask(self, agent_id: str, question: str) -> Dict[str, Any]:
        result = self.queue.submit(agent_id, question)
        if result == "rate_limited":
            return {"status": "rate_limited", "answer": None}

        answers = self.queue.process()
        for a in answers:
            if a["agent_id"] == agent_id and a["question"] == question:
                return {"status": "ok", "answer": a["answer"]}

        return {"status": "queued", "answer": None}
