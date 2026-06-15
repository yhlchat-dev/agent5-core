# -*- coding: utf-8 -*-
import logging


from typing import Any, Dict
class DataFilter:

    def __init__(self) -> None:
        self.logger = logging.getLogger("DataFilter")

    def filter(self, context: Dict[str, Any], mode: str = 'safe') -> Dict[str, Any]:
        if mode == "full":
            return context

        if mode == "balanced":
            return {
                "input": context.get("input"),
                "output": context.get("output"),
                "summary": context.get("summary"),
            }

        return {
            "input": context.get("input"),
            "output": context.get("output"),
        }
