# -*- coding: utf-8 -*-
import time
import logging
from typing import Any, Callable, Dict, List, Optional

from core.runtime.execution_engine import ExecutionEngine


class UnifiedCoordinator:

    def __init__(self, registry: Optional[Any] = None, event_bus: Dict[str, Any] = None) -> None:
        self.registry = registry
        self.event_bus = event_bus
        self._coordinators: Dict[str, Any] = {}
        self._routes: Dict[str, str] = {}
        self.logger = logging.getLogger("UnifiedCoordinator")
        self.engine = ExecutionEngine()

    def register_coordinator(self, name: str, coordinator: Any) -> None:
        self._register_coordinator_impl(name, coordinator)
        self.logger.info(f"[UnifiedCoordinator] registered: {name}")

    def _register_coordinator_impl(self, name: str, coordinator: Any) -> None:
        self._coordinators[name] = coordinator

    def register_route(self, task_type: str, coordinator_name: str) -> None:
        self._register_route_impl(task_type, coordinator_name)
        self.logger.info(f"[UnifiedCoordinator] route: {task_type} → {coordinator_name}")

    def _register_route_impl(self, task_type: str, coordinator_name: str) -> None:
        self._routes[task_type] = coordinator_name

    def handle(self, task_or_result: Dict[str, Any]) -> Dict:
        if isinstance(task_or_result, dict) and task_or_result.get('action') == 'execute':
            return self.engine.execute(task_or_result)

        task = task_or_result
        task_type = task.get("type", "unknown") if isinstance(task, dict) else "unknown"
        start_time = time.time()

        if isinstance(task, dict) and task.get("target") == "controller" and self.registry:
            result = self._handle_controller_task(task, task_type, start_time)
            if isinstance(result, dict) and result.get('action') == 'execute':
                return self.engine.execute(result)
            return result

        result = self._handle_routed_task(task, task_type)
        duration = time.time() - start_time
        self._emit_handled_event(task_type, duration, result)

        if isinstance(result, dict) and result.get('action') == 'execute':
            return self.engine.execute(result)

        return result

    def _handle_controller_task(self, task: dict, task_type: str, start_time: float) -> Dict:
        kernel = self.registry.get("kernel_boot") if self.registry else None
        if kernel and hasattr(kernel, 'route_task'):
            return kernel.route_task(task)

        controller = self.registry.get("controller") if self.registry else None
        if not controller:
            return {}

        result = self._dispatch_controller(controller, task)
        duration = time.time() - start_time
        self._emit_handled_event(task_type, duration, result)
        return result

    def _dispatch_controller(self, controller, task: dict):
        _DISPATCH_METHODS = ['decide', 'execute', 'handle']
        for method_name in _DISPATCH_METHODS:
            if hasattr(controller, method_name):
                return getattr(controller, method_name)(task)
        return self._dispatch(controller, task)

    def _handle_routed_task(self, task: dict, task_type: str) -> Dict:
        coordinator_name = self._routes.get(task_type) if isinstance(task, dict) else None
        if coordinator_name and coordinator_name in self._coordinators:
            coordinator = self._coordinators[coordinator_name]
            return self._dispatch(coordinator, task)
        return self._default_handle(task)

    def _emit_handled_event(self, task_type: str, duration: float, result) -> None:
        if self.event_bus:
            self.event_bus.emit("coordinator.handled", {
                "task_type": task_type,
                "duration": duration,
                "status": result.get("status") if isinstance(result, dict) else None,
            })

    def _dispatch(self, coordinator, task: Dict) -> Dict:
        if hasattr(coordinator, "handle_task"):
            return coordinator.handle_task(task)
        if hasattr(coordinator, "handle"):
            return coordinator.handle(task)
        if callable(coordinator):
            return coordinator(task)
        return {"status": "failed", "reason": "coordinator_no_handle_method"}

    def _default_handle(self, task: Dict) -> Dict:
        if self.registry:
            controller = self.registry.get("controller")
            if controller and hasattr(controller, "coordinator"):
                return controller.coordinator.handle_task(task)

        return {"status": "ok", "msg": "runtime fallback ok", "task": task}

    def get_status(self) -> Dict:
        return {
            "coordinators": list(self._coordinators.keys()),
            "routes": dict(self._routes),
        }
