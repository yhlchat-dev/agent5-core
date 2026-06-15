# -*- coding: utf-8 -*-
import logging
import threading
from typing import Any, Callable, Dict, List, Optional


class EventBus:

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()
        self._history: List[Dict] = []
        self._max_history = 500
        self.logger = logging.getLogger("EventBus")

    def on(self, event_type: str, handler: Callable) -> str:
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
        return f"{event_type}:{id(handler)}"

    def off(self, event_type: str, handler: Optional[Callable] = None) -> None:
        with self._lock:
            if event_type not in self._subscribers:
                return
            if handler is None:
                del self._subscribers[event_type]
            else:
                self._subscribers[event_type] = [
                    h for h in self._subscribers[event_type] if h != handler
                ]

    def emit(self, event_type: str, data: Any = None) -> None:
        import time
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            handlers = list(self._subscribers.get(event_type, []))
            wildcard_handlers = list(self._subscribers.get("*", []))

        for handler in handlers + wildcard_handlers:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(f"[EventBus] handler error on '{event_type}': {e}")

    def once(self, event_type: str, handler: Callable) -> None:
        def wrapper(event: Dict[str, Any]) -> None:
            self.off(event_type, wrapper)
            handler(event)
        self.on(event_type, wrapper)

    def get_history(self, event_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            events = self._history
            if event_type:
                events = [e for e in events if e["type"] == event_type]
            return events[-limit:]

    def subscriber_count(self, event_type: Optional[str] = None) -> int:
        with self._lock:
            if event_type:
                return len(self._subscribers.get(event_type, []))
            return sum(len(v) for v in self._subscribers.values())

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()
            self._history.clear()
