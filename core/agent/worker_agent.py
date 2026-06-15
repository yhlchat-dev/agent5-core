from typing import Any, Dict, List, Optional
"""
Worker Agent模块
执行单一职责任务的工作代理
"""
import asyncio
import uuid
import gc
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from core.agent.task_model import Task, TaskResult, TaskStatus
from core.utils.logger import get_logger


class WorkerState(Enum):
    """Worker状态枚举"""
    # [枚举值] - 无需迁移
    IDLE = "idle"
    # [枚举值] - 无需迁移
    BUSY = "busy"
    # [枚举值] - 无需迁移
    STOPPED = "stopped"
    # [枚举值] - 无需迁移
    ERROR = "error"


@dataclass
class WorkerStats:
    """Worker统计"""
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_duration: float = 0.0
    last_task_at: Optional[datetime] = None
    created_at: float = field(default_factory=time.time)
    busy_since: Optional[float] = None


class WorkerAgent:
    """
    Worker代理
    执行单一职责任务
    支持强制销毁和心跳检测
    """
    
    def __init__(self, worker_id: str = None, capabilities: List[str] = None) -> None:
        self.worker_id = worker_id or str(uuid.uuid4())[:8]
        self.capabilities = capabilities or ["generic"]
        self.state = WorkerState.IDLE
        self.current_task: Optional[Task] = None
        self.stats = WorkerStats()
        self.logger = get_logger(f"agent.worker.{self.worker_id}")
        self.llm_client: Optional[Any] = None
        self.last_heartbeat: float = time.time()
        
        self._task_handlers: Dict[str, Callable] = {}
        self._running = False
        self._current_async_task: Optional[asyncio.Task] = None
        self._heartbeat: float = time.time()
    
    def register_handler(self, task_type: str, handler: Callable) -> None:
        self._register_handler_impl(task_type, handler)

    def _register_handler_impl(self, task_type: str, handler: Callable) -> None:
        self._task_handlers[task_type] = handler
    
    def can_handle(self, task: Task) -> bool:
        if task.task_type in self._task_handlers:
            return True
        if task.task_type in self.capabilities:
            return True
        return "generic" in self.capabilities
    
    def update_heartbeat(self) -> bool:
        self._heartbeat = time.time()
        self.last_heartbeat = self._heartbeat
    
    def get_heartbeat_age(self) -> float:
        return time.time() - self._heartbeat
    
    def get_busy_duration(self) -> float:
        if self.state == WorkerState.BUSY and self.stats.busy_since:
            return time.time() - self.stats.busy_since
        return 0.0

    def is_zombie(self, threshold: float = 90.0) -> bool:
        if self.state != WorkerState.BUSY:
            return False
        heartbeat_age = self.get_heartbeat_age()
        busy_duration = self.get_busy_duration()
        return heartbeat_age > threshold and busy_duration > threshold

    def register_resource(self, resource_type: str, resource: Any = None) -> None:
        self._register_resource_impl(resource_type, resource)

    def _register_resource_impl(self, resource_type: str, resource: Any = None) -> None:
        if not hasattr(self, '_tracked_resources'):
            self._tracked_resources = {}
        self._tracked_resources[resource_type] = {
            "resource": resource,
            "registered_at": time.time(),
        }

    def get_tracked_resources(self) -> Dict[str, Any]:
        return getattr(self, '_tracked_resources', {})

    async def execute(self, task: Task) -> TaskResult:
        if not self._can_execute(task):
            return self._reject_task(task)
        self._mark_busy(task)
        try:
            return await self._execute_task(task)
        except Exception as e:
            self.logger.error(f"任务执行失败: {e}")
            task.fail(str(e))
            self.stats.tasks_failed += 1
            return TaskResult(task_id=task.id, success=False, error=str(e))
        finally:
            self._mark_idle()

    def _can_execute(self, task: Task) -> bool:
        if self.state == WorkerState.STOPPED:
            return False
        if not task:
            return False
        return True

    def _reject_task(self, task: Task) -> TaskResult:
        return TaskResult(
            task_id=getattr(task, 'id', 'unknown'),
            success=False,
            error="Worker已停止" if self.state == WorkerState.STOPPED else "invalid input: task required"
        )

    def _mark_busy(self, task: Task) -> None:
        self.state = WorkerState.BUSY
        self.current_task = task
        self.stats.busy_since = time.time()
        self.update_heartbeat()
        task.start(self.worker_id)

    async def _execute_task(self, task: Task) -> TaskResult:
        start_time = datetime.now()
        self.logger.info(f"开始执行任务: {task.name} ({task.id})")
        handler = self._task_handlers.get(task.task_type, self._default_handler)
        try:
            if asyncio.iscoroutinefunction(handler):
                self._current_async_task = asyncio.create_task(
                    asyncio.wait_for(handler(task), timeout=task.timeout)
                )
                result = await self._current_async_task
            else:
                self._current_async_task = asyncio.create_task(
                    asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, handler, task),
                        timeout=task.timeout
                    )
                )
                result = await self._current_async_task
        except asyncio.TimeoutError:
            task.timeout_task()
            return TaskResult(task_id=task.id, success=False, error="任务执行超时")
        except asyncio.CancelledError:
            self.logger.warning(f"任务被强制取消: {task.name}")
            return TaskResult(task_id=task.id, success=False, error="任务被强制取消")

        task.complete(result)
        self.stats.tasks_completed += 1
        self.stats.total_duration += (datetime.now() - start_time).total_seconds()
        self.stats.last_task_at = datetime.now()
        self.logger.info(f"任务完成: {task.name}")
        return TaskResult(task_id=task.id, success=True, result=result, duration=task.get_duration())

    def _mark_idle(self) -> None:
        self.state = WorkerState.IDLE
        self.current_task = None
        self._current_async_task = None
        self.stats.busy_since = None
        self.update_heartbeat()
    
    def force_stop(self) -> bool:
        """强制停止Worker，取消当前任务"""
        self.logger.warning(f"强制停止Worker: {self.worker_id}, 当前状态: {self.state.value}")
        
        if self._current_async_task and not self._current_async_task.done():
            self._current_async_task.cancel()
            self.logger.info(f"已取消Worker {self.worker_id} 的异步任务")
        
        self.state = WorkerState.STOPPED
        self._running = False
        self.current_task = None
        self._current_async_task = None
        self.stats.busy_since = None
        
        return True

    def _default_handler(self, task: Task) -> Any:
        return self._default_handler_impl(task)

    def _default_handler_impl(self, task: Task) -> Any:
        return {"status": "processed", "task_type": task.task_type}
    
    def stop(self) -> None:
        """停止Worker"""
        self._stop_impl()

    def _stop_impl(self) -> None:
        self.state = WorkerState.STOPPED
        self._running = False
    
    def start(self) -> None:
        """启动Worker"""
        self._start_impl()

    def _start_impl(self) -> None:
        self.state = WorkerState.IDLE
        self._running = True
        self.update_heartbeat()
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "state": self.state.value,
            "capabilities": self.capabilities,
            "current_task": self.current_task.id if self.current_task else None,
            "heartbeat_age": round(self.get_heartbeat_age(), 1),
            "busy_duration": round(self.get_busy_duration(), 1),
            "is_zombie": self.is_zombie(),
            "has_llm_client": self.llm_client is not None,
            "stats": {
                "tasks_completed": self.stats.tasks_completed,
                "tasks_failed": self.stats.tasks_failed,
                "total_duration": self.stats.total_duration,
                "last_task_at": self.stats.last_task_at.isoformat() if self.stats.last_task_at else None,
                "created_at": self.stats.created_at,
            }
        }
