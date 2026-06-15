# -*- coding: utf-8 -*-
"""
EventBus — Phase 7.6 轻量事件总线

事件类型：
- ON_STEP: 每步执行
- ON_REWARD: reward 计算
- ON_CONSTITUTION_APPLY: 宪法规则应用
- ON_EPISODE_END: episode 结束

纯发布-订阅模式，不参与决策。
"""
import threading
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict
from datetime import datetime


# 事件类型常量
ON_STEP = "on_step"
ON_REWARD = "on_reward"
ON_CONSTITUTION_APPLY = "on_constitution_apply"
ON_EPISODE_END = "on_episode_end"


class Event:
    """事件对象"""

    def __init__(self, event_type: str, data: Optional[Dict[str, Any]] = None):
        self.type = event_type
        self.data = data or {}
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class EventBus:
    """轻量事件总线

    发布-订阅模式，observer 模块通过 subscribe 注册回调，
    核心模块通过 emit 发布事件。
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self._emit_count: int = 0

    def subscribe(self, event_type: str, callback: Callable[[Event], None]) -> None:
        """订阅事件"""
        with self._lock:
            self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Event], None]) -> None:
        """取消订阅"""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    cb for cb in self._subscribers[event_type] if cb != callback
                ]

    def emit(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> Event:
        """发布事件"""
        event = Event(event_type, data)
        self._emit_count += 1

        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                pass  # 观测层不应影响主流程

        return event

    @property
    def emit_count(self) -> int:
        return self._emit_count

    def get_stats(self) -> Dict[str, Any]:
        return {
            "emit_count": self._emit_count,
            "subscriber_count": {
                et: len(cbs) for et, cbs in self._subscribers.items()
            },
        }


# 全局单例
_global_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """获取全局 EventBus 单例"""
    global _global_bus
    if _global_bus is None:
        with _bus_lock:
            if _global_bus is None:
                _global_bus = EventBus()
    return _global_bus
