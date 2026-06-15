# -*- coding: utf-8 -*-
from typing import Any, Dict, Optional
"""
Memory Router — 记忆路由核心

将记忆事件路由到对应的记忆层：
  raw_trace  → working   (工作记忆)
  short_term → episodic  (情景记忆)
  pattern    → semantic  (语义记忆)
  identity   → self      (自我记忆)
"""
import logging
from typing import Dict, Any, Optional


class MemoryRouter:
    """
    记忆路由器：根据事件类型决定写入哪一层记忆。
    """

    # [可配置] - 建议迁移到 YAML
    ROUTE_MAP = {
        "raw_trace": "working",
        "short_term": "episodic",
        "pattern": "semantic",
        "identity": "self",
        "working": "working",
        "episodic": "episodic",
        "semantic": "semantic",
        "self": "self",
    }

    # [枚举值] - 无需迁移
    DEFAULT_ROUTE = "episodic"

    def __init__(self) -> None:
        self.custom_routes = {}
        self.logger = logging.getLogger("MemoryRouter")
        self._route_stats = {
            "working": 0,
            "episodic": 0,
            "semantic": 0,
            "self": 0,
        }

    def route(self, memory_event: Dict[str, Any]) -> str:
        """
        根据事件类型路由到对应记忆层。

        Args:
            memory_event: 记忆事件，可以是 dict 或有 type 属性的对象

        Returns:
            层名称: "working" / "episodic" / "semantic" / "self"
        """
        event_type = self._extract_type(memory_event)

        if event_type in self.custom_routes:
            layer = self.custom_routes[event_type]
        elif event_type in self.ROUTE_MAP:
            layer = self.ROUTE_MAP[event_type]
        else:
            importance = self._extract_importance(memory_event)
            layer = self._route_by_importance(importance)
            self.logger.debug(
                "未知事件类型 '{}', 按重要性路由到 '{}'".format(event_type, layer)
            )

        self._route_stats[layer] = self._route_stats.get(layer, 0) + 1
        return layer

    def _extract_type(self, event: Dict[str, Any]) -> str:
        if isinstance(event, dict):
            return event.get("type", "unknown")
        if hasattr(event, 'type'):
            return event.type
        return "unknown"

    def _extract_importance(self, event: Dict[str, Any]) -> float:
        if isinstance(event, dict):
            return event.get("importance", 0.5)
        if hasattr(event, 'importance'):
            return event.importance
        return 0.5

    def _route_by_importance(self, importance: float) -> str:
        if importance >= 0.85:
            return "self"
        if importance >= 0.6:
            return "semantic"
        return "episodic"

    def register_route(self, event_type: str, layer: str) -> None:
        """
        注册自定义路由规则。
        """
        if layer not in ("working", "episodic", "semantic", "self"):
            self.logger.warning("无效的记忆层: '{}'".format(layer))
            return
        self.custom_routes[event_type] = layer

    def get_stats(self) -> Dict[str, Any]:
        total = sum(self._route_stats.values())
        return {
            "route_counts": dict(self._route_stats),
            "total_routed": total,
            "custom_routes": dict(self.custom_routes),
        }
