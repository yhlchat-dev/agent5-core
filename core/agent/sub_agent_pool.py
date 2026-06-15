# -*- coding: utf-8 -*-
import logging


from typing import Any, List, Optional
class SubAgentPool:

    def __init__(self, agents: Optional[Any] = None) -> None:
        self.agents = agents or []
        self.logger = logging.getLogger("SubAgentPool")

    def add(self, agent) -> list:
        self.agents.append(agent)

    def remove(self, agent) -> list:
        self.agents = [a for a in self.agents if a is not agent]

    def get_available(self) -> list:
        return [a for a in self.agents if getattr(a, "available", True)]

    def get_all(self) -> List[Any]:
        return list(self.agents)

    def count(self) -> int:
        return len(self.agents)

    def count_available(self) -> int:
        return len(self.get_available())

    def get_least_loaded(self) -> None:
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda a: getattr(a, "load", 0))
