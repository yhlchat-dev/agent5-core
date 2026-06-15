# -*- coding: utf-8 -*-
import logging


from typing import Any, Dict
class ContextBuilder:

    def __init__(self) -> None:
        self.logger = logging.getLogger("ContextBuilder")

    def build(self, task: Any, result: Dict[str, Any], memory: Any) -> Dict[str, Any]:
        return {
            "input": task.get("input") if isinstance(task, dict) else getattr(task, "input", None),
            "output": result.get("output") if isinstance(result, dict) else getattr(result, "output", None),
            "summary": result.get("summary") if isinstance(result, dict) else getattr(result, "summary", None),
            "chain": result.get("chain") if isinstance(result, dict) else getattr(result, "chain", None),
            "env": result.get("env") if isinstance(result, dict) else getattr(result, "env", None),
            "memory": memory,
        }
