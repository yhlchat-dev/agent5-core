# -*- coding: utf-8 -*-
import logging
import uuid


from typing import Any, Dict
class Planner:

    def __init__(self, bus) -> None:
        self.bus = bus
        self.logger = logging.getLogger("Planner")
        self.bus.subscribe("goal.received", self._on_goal)

    def _on_goal(self, event: Dict[str, Any]) -> None:
        payload = event.get("payload", {})
        goal_type = payload.get("type")

        if goal_type == "login":
            plan = [
                {"id": str(uuid.uuid4()), "action_type": "browser.type", "payload": {"selector": "#username", "text": payload.get("username")}},
                {"id": str(uuid.uuid4()), "action_type": "browser.type", "payload": {"selector": "#password", "text": payload.get("password")}},
                {"id": str(uuid.uuid4()), "action_type": "browser.click", "payload": {"selector": "#login-btn"}},
            ]

            self.bus.emit({
                "type": "plan.created",
                "payload": {"steps": plan},
            })
        else:
            self.bus.emit({
                "type": "plan.failed",
                "payload": {"reason": "unknown_goal"},
            })
