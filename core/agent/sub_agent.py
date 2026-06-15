# -*- coding: utf-8 -*-
import logging
from core.utils.logger import get_logger
from core.safety.agent_guard import AgentGuard, GuardBlockedError
from core.capsule.capsule_manager import CapsuleManager
from core.privacy.data_label import get_label, check_data_access, sanitize_data, DataLabel


from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class SubAgentInitContext:
    guard: Optional[Any] = None
    capsule_manager: Optional[Any] = None
    dag_executor: Optional[Any] = None
    task_context_manager: Optional[Any] = None
    raw_event_store: Optional[Any] = None


class SubAgent:

    def __init__(self, guard: Optional[Any] = None, capsule_manager: Optional[Any] = None, dag_executor: Optional[Any] = None, task_context_manager: Optional[Any] = None, raw_event_store: Optional[Any] = None) -> None:
        ctx = SubAgentInitContext(guard=guard, capsule_manager=capsule_manager, dag_executor=dag_executor, task_context_manager=task_context_manager, raw_event_store=raw_event_store)
        self._init_with_context(ctx)

    def _init_with_context(self, ctx: SubAgentInitContext) -> None:
        self.guard = ctx.guard or AgentGuard()
        self.capsule_manager = ctx.capsule_manager
        self.dag_executor = ctx.dag_executor
        self.task_context_manager = ctx.task_context_manager
        self.raw_event_store = ctx.raw_event_store
        self.name = "sub_agent"
        self.load = 0
        self.available = True
        self.logger = get_logger("SubAgent")

    async def act(self, task: Task, context: Dict[str, Any] = None) -> Dict[str, Any]:
        task_type = getattr(task, "type", task.get("type", "unknown"))
        operation = getattr(task, "operation", task.get("operation", "execute"))
        params = getattr(task, "params", task.get("params", {}))
        task_id = getattr(task, "id", id(task))

        self.guard.check(action=task_type, operation=operation, params=params)

        if self.task_context_manager:
            self.task_context_manager.create(task_id)

        try:
            if self.dag_executor and hasattr(task, "to_dag"):
                dag = task.to_dag()
                if dag:
                    return self._execute_dag(task_id, task_type, dag)

            return await self._execute_capsule(task_id, task_type, params, context)
        finally:
            if self.task_context_manager:
                self.task_context_manager.clear(task_id)

    def _execute_dag(self, task_id: str, task_type: str, dag) -> Dict[str, Any]:
        self.load += 1
        result = self.dag_executor.execute(dag)
        self.load = max(0, self.load - 1)
        self._record_event(task_id, task_type, result)
        return result

    async def _execute_capsule(self, task_id: str, task_type: str, params, context) -> Dict[str, Any]:
        if self.capsule_manager:
            params, context = self._sanitize_params(params, context)
            result = await self.capsule_manager.run(f"{task_type}_capsule", params, context)
            self._record_event(task_id, task_type, {"status": "success", "data": result})
            return {"status": "success", "data": result}
        result = {"status": "success", "data": {"action": task_type}}
        self._record_event(task_id, task_type, result)
        return result

    def _sanitize_params(self, params, context) -> tuple:
        caller = self.name
        if isinstance(params, dict):
            label = get_label(params)
            if label is not None and not check_data_access(params, caller, DataLabel.INTERNAL):
                self.logger.warning("[SubAgent] Privacy label check: params label=%s denied for caller=%s, sanitizing", label.name, caller)
                params = sanitize_data(params, caller)
        if isinstance(context, dict):
            ctx_label = get_label(context)
            if ctx_label is not None and not check_data_access(context, caller, DataLabel.INTERNAL):
                self.logger.warning("[SubAgent] Privacy label check: context label=%s denied for caller=%s, sanitizing", ctx_label.name, caller)
                context = sanitize_data(context, caller)
        return params, context

    def execute(self, task: Task) -> None:
        task_type = getattr(task, "type", None)
        if task_type is None and isinstance(task, dict):
            task_type = task.get("type", "unknown")
        params = getattr(task, "params", None)
        if params is None and isinstance(task, dict):
            params = task.get("params", {})
        task_id = getattr(task, "id", id(task))

        if self.task_context_manager:
            self.task_context_manager.create(task_id)

        try:
            if self.dag_executor and hasattr(task, "to_dag"):
                dag = task.to_dag()
                if dag:
                    self.load += 1
                    result = self.dag_executor.execute(dag)
                    self.load = max(0, self.load - 1)
                    self._record_event(task_id, task_type, result)
                    return result

            result = {"status": "success", "data": {"action": task_type, "params": params}}
            self._record_event(task_id, task_type, result)
            return result
        finally:
            if self.task_context_manager:
                self.task_context_manager.clear(task_id)

    def _record_event(self, task_id: str, task_type, result: Any) -> None:
        if self.raw_event_store:
            self.raw_event_store.append({
                "task_id": task_id,
                "task_type": task_type,
                "result": result,
                "agent": self.name,
            })
