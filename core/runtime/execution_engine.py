from core.runtime.action_router import ActionRouter


from typing import Any, Dict, Optional


class ExecutionEngine:

    def __init__(self) -> None:
        self.router = ActionRouter()

    def execute(self, decision: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(decision, dict):
            return {"error": "invalid input: decision must be dict"}
        task = decision.get("task", {})
        return self.router.route(task)

