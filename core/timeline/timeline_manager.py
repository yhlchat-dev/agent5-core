# -*- coding: utf-8 -*-
import logging
import time
import uuid
from core.utils.config_loader import get_config


from typing import Any, Dict, Optional
class TimelineManager:

    def __init__(self, max_size: int = None) -> None:
        self.events = []
        self.max_size = max_size or get_config('global.limits.timeline_max_size', 1000)
        self.causal_engine = None
        self.event_store = None
        self._logger = logging.getLogger("TimelineManager")

    def bind_event_store(self, event_store) -> None:
        """绑定 EventStore，record() 时自动持久化"""
        self.event_store = event_store

    def record(self, event_type, **kwargs) -> None:
        event = {
            "ts": time.time(),
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            **kwargs
        }

        self.events.append(event)

        if self.causal_engine:
            self.causal_engine.ingest_timeline_event(event)

        # 自动持久化到 EventStore（异常隔离）
        if self.event_store:
            try:
                self.event_store.save(
                    event_type=str(event_type),
                    data=kwargs,
                    importance=kwargs.get("importance", 0.5),
                )
            except Exception as e:
                self._logger.debug(f"EventStore save failed: {e}")

        if len(self.events) > self.max_size:
            self.events = self.events[-self.max_size:]

    def get_recent(self, n: int = 50) -> Any:
        return self.events[-n:]

    def get_all(self) -> None:
        return self.events

    def get_by_failure(self, failure_type) -> None:
        return [
            e for e in self.events
            if e.get("failure_type") == failure_type
        ]
