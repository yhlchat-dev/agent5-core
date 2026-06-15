from typing import Any, Dict, List, Optional
"""
Agent Manager模块 - Facade
管理Worker池，动态扩缩容，超时回收
支持强制销毁、定期清理、内存监控

子模块:
- agent.resource_tracker: Worker资源追踪
- agent.worker_pool: Worker生命周期管理
"""
import asyncio
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from core.agent.worker_agent import WorkerAgent, WorkerState
from core.agent.task_model import Task, TaskResult, TaskPriority, TaskStatus
from core.agent.resource_tracker import ResourceTracker
from core.agent.worker_pool import WorkerPool, DestroyLog
from core.utils.config_loader import ConfigLoader, get_config
from core.utils.logger import get_logger


@dataclass
class ManagerStats:
    total_workers_created: int = 0
    total_workers_destroyed: int = 0
    total_workers_force_destroyed: int = 0
    total_tasks_dispatched: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0


class AgentManager:
    """
    Agent管理器 (Facade)
    管理Worker池，动态扩缩容，超时回收
    支持强制销毁、定期清理、内存监控

    Worker生命周期委托给 WorkerPool
    资源追踪委托给 ResourceTracker
    """

    # [可配置] - 已迁移到 config/agent_params.yaml
    BUSY_TIMEOUT_SECONDS = get_config('agent.worker.busy_timeout', 180)
    # [可配置] - 已迁移到 config/agent_params.yaml
    IDLE_TIMEOUT_SECONDS = get_config('agent.worker.idle_timeout', 300)
    # [可配置] - 建议迁移到 YAML
    CLEANUP_INTERVAL_SECONDS = 45
    # [可配置] - 已迁移到 config/agent_params.yaml
    ZOMBIE_HEARTBEAT_THRESHOLD = get_config('agent.worker.zombie_threshold', 90)

    def __init__(self, config_loader: ConfigLoader = None) -> None:
        self.config_loader = config_loader or ConfigLoader()
        self.config = self.config_loader.get_config("agent_config.yaml")
        self.logger = get_logger("agent.manager")

        agent_config = self.config.get('agent', {})
        self.max_workers = agent_config.get('max_workers', 30)
        self.worker_timeout = agent_config.get('worker_timeout', 120)

        self._resource_tracker = ResourceTracker()
        self._worker_pool = WorkerPool(
            max_workers=self.max_workers,
            resource_tracker=self._resource_tracker
        )

        self._task_queue: asyncio.PriorityQueue = None
        self._results: Dict[str, TaskResult] = {}
        self._stats = ManagerStats()
        self._task_counter = 0

        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    def _get_or_create_loop(self) -> asyncio.AbstractEventLoop:
        try:
            loop = asyncio.get_running_loop()
            return loop
        except RuntimeError:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop

    def _run_async(self, coro: Any) -> None:
        loop = self._get_or_create_loop()
        try:
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except Exception as e:
            self.logger.error(f"运行异步任务失败: {e}")
            raise

    async def initialize(self) -> None:
        self._initialize_impl()

    def _initialize_impl(self) -> None:
        self._task_queue = asyncio.PriorityQueue()
        self._running = True

    def sync_initialize(self) -> None:
        self._run_async(self.initialize())

    def register_task_handler(self, task_type: str, handler: Callable) -> None:
        self._register_task_handler_impl(task_type, handler)

    def _register_task_handler_impl(self, task_type: str, handler: Callable) -> None:
        self._worker_pool.register_task_handler(task_type, handler)

    def register_task_handlers(self, handlers: Dict[str, Callable]) -> None:
        self._register_task_handlers_impl(handlers)

    def _register_task_handlers_impl(self, handlers: Dict[str, Callable]) -> None:
        self._worker_pool.register_task_handlers(handlers)

    async def create_worker(self, capabilities: List[str] = None) -> WorkerAgent:
        worker = await self._worker_pool.create_worker(capabilities)
        self._stats.total_workers_created += 1
        return worker

    def sync_create_worker(self, capabilities: List[str] = None) -> WorkerAgent:
        worker = self._worker_pool.sync_create_worker(capabilities)
        self._stats.total_workers_created += 1
        return worker

    async def destroy_worker(self, worker_id: str, force: bool = False, reason: str = "") -> bool:
        result = await self._worker_pool.destroy_worker(worker_id, force, reason)
        if result:
            self._stats.total_workers_destroyed += 1
            if force:
                self._stats.total_workers_force_destroyed += 1
        return result

    def sync_destroy_worker(self, worker_id: str, force: bool = False, reason: str = "") -> bool:
        result = self._worker_pool.sync_destroy_worker(worker_id, force, reason)
        if result:
            self._stats.total_workers_destroyed += 1
            if force:
                self._stats.total_workers_force_destroyed += 1
        return result

    async def submit_task(self, task: Task) -> str:
        return await self._submit_task_impl(task)

    async def _submit_task_impl(self, task: Task) -> str:
        self._task_counter += 1
        await self._task_queue.put((task.priority.value, task.created_at.timestamp(), self._task_counter, task))
        self._stats.total_tasks_dispatched += 1
        return task.id

    def sync_submit_task(self, task: Task) -> str:
        return self._run_async(self.submit_task(task))

    async def get_result(self, task_id: str, timeout: float = None) -> Optional[TaskResult]:
        start_time = datetime.now()
        while True:
            if task_id in self._results:
                return self._results.pop(task_id)
            if timeout:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= timeout:
                    return None
            await asyncio.sleep(float(get_config("constants.sleep.default", 0.1)))

    def sync_get_result(self, task_id: str, timeout: float = None) -> Optional[TaskResult]:
        return self._run_async(self.get_result(task_id, timeout))

    async def dispatch(self) -> None:
        while self._running:
            try:
                if self._task_queue.empty():
                    await asyncio.sleep(float(get_config("constants.sleep.default", 0.1)))
                    continue

                _, _, _, task = await self._task_queue.get()
                worker = await self._worker_pool.find_available_worker(task)

                if worker is None:
                    self._task_counter += 1
                    await self._task_queue.put((task.priority.value, task.created_at.timestamp(), self._task_counter, task))
                    await asyncio.sleep(float(get_config("constants.sleep.default", 0.2)))
                    continue

                self._worker_pool.mark_busy(worker.worker_id)
                asyncio.create_task(self._execute_and_collect(worker, task))

            except Exception as e:
                self.logger.error(f"调度错误: {e}")
                await asyncio.sleep(float(get_config("constants.sleep.default", 0.1)))

    async def _execute_and_collect(self, worker: WorkerAgent, task: Task) -> None:
        try:
            result = await worker.execute(task)
            self._results[task.id] = result
            if result.success:
                self._stats.total_tasks_completed += 1
            else:
                self._stats.total_tasks_failed += 1
        except Exception as e:
            self.logger.error(f"执行任务异常: {e}")
            self._results[task.id] = TaskResult(task_id=task.id, success=False, error=str(e))
            self._stats.total_tasks_failed += 1
        finally:
            self._worker_pool.mark_idle(worker.worker_id)

    async def cleanup_idle_workers(self, max_idle_time: int = 300) -> int:
        return await self._worker_pool.cleanup_idle_workers(max_idle_time)

    def sync_cleanup_idle_workers(self, max_idle_time: int = 300) -> int:
        return self._run_async(self.cleanup_idle_workers(max_idle_time))

    async def start(self) -> None:
        await self._start_impl()

    async def _start_impl(self) -> None:
        await self.initialize()
        asyncio.create_task(self.dispatch())
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    def sync_start(self) -> None:
        self._run_async(self.start())

    async def stop(self) -> None:
        await self._stop_impl()

    async def _stop_impl(self) -> None:
        self._running = False
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        for worker_id in list(self._worker_pool.workers.keys()):
            await self.destroy_worker(worker_id, force=True, reason="管理器停止")

    def sync_stop(self) -> None:
        self._run_async(self.stop())

    async def _periodic_cleanup(self) -> None:
        while self._running:
            try:
                warnings, error = await self._periodic_cleanup_impl()
                for warning in warnings:
                    self.logger.warning(f"[内存泄漏预警] {warning}")
                if error is not None:
                    self.logger.error(f"定期清理异常: {error}")
            except asyncio.CancelledError:
                break

    async def _periodic_cleanup_impl(self) -> tuple:
        warnings = []
        error = None
        try:
            await asyncio.sleep(self.CLEANUP_INTERVAL_SECONDS)
            await self._worker_pool.cleanup_zombie_workers()
            await self._worker_pool.cleanup_idle_workers(max_idle_time=self.IDLE_TIMEOUT_SECONDS)
            current_mem = self._worker_pool._get_memory_mb()
            for wid in list(self._worker_pool.workers.keys()):
                self._resource_tracker.record_memory_peak(wid, current_mem)
                warning = self._resource_tracker.check_leak_warning(wid, current_mem)
                if warning:
                    warnings.append(warning)
        except Exception as e:
            error = e
        return warnings, error

    def get_status(self) -> Dict[str, Any]:
        mem_mb = self._worker_pool._get_memory_mb()
        return {
            "running": self._running,
            "total_workers": len(self._worker_pool.workers),
            "idle_workers": self._worker_pool.get_idle_worker_count(),
            "busy_workers": self._worker_pool.get_busy_worker_count(),
            "max_workers": self.max_workers,
            "queue_size": self._task_queue.qsize() if self._task_queue else 0,
            "pending_results": len(self._results),
            "memory_mb": round(mem_mb, 1),
            "resource_tracker": self._resource_tracker.get_all_tracked(),
            "stats": {
                "total_workers_created": self._stats.total_workers_created,
                "total_workers_destroyed": self._stats.total_workers_destroyed,
                "total_workers_force_destroyed": self._stats.total_workers_force_destroyed,
                "total_tasks_dispatched": self._stats.total_tasks_dispatched,
                "total_tasks_completed": self._stats.total_tasks_completed,
                "total_tasks_failed": self._stats.total_tasks_failed,
            },
            "recent_destroy_logs": [
                {"worker_id": l.worker_id, "reason": l.reason, "was_busy": l.was_busy,
                 "mem_before": l.memory_before_mb, "mem_after": l.memory_after_mb,
                 "resources_released": l.resources_released}
                for l in self._worker_pool.destroy_logs[-5:]
            ]
        }

    def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        return self._worker_pool.get_worker_status(worker_id)

    def get_all_workers(self) -> List[Dict[str, Any]]:
        return self._worker_pool.get_all_workers()

    def get_active_workers(self) -> List[str]:
        return self._worker_pool.get_active_workers()

    def get_idle_worker_count(self) -> int:
        return self._worker_pool.get_idle_worker_count()

    def get_busy_worker_count(self) -> int:
        return self._worker_pool.get_busy_worker_count()

    def create_agent(self, config: Dict[str, Any] = None) -> str:
        capabilities = config.get("capabilities") if isinstance(config, dict) else None
        worker = self.sync_create_worker(capabilities=capabilities)
        return worker.worker_id

    def get_agent(self, agent_id: str) -> Optional[Any]:
        return self._worker_pool.workers.get(agent_id)

    def terminate_agent(self, agent_id: str) -> bool:
        return self.sync_destroy_worker(agent_id, force=True, reason="terminate_agent")
