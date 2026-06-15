import asyncio
import gc
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.agent.worker_agent import WorkerAgent, WorkerState
from core.agent.task_model import Task, TaskResult
from core.agent.resource_tracker import ResourceTracker
from core.utils.config_loader import get_config
from core.utils.logger import get_logger

logger = get_logger("agent.worker_pool")


@dataclass
class DestroyLog:
    worker_id: str
    reason: str
    was_busy: bool
    memory_before_mb: float
    memory_after_mb: float
    resources_released: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=__import__('time').time)


class WorkerPool:

    # [可配置] - 已迁移到 config/agent_params.yaml
    BUSY_TIMEOUT_SECONDS = get_config('agent.worker.busy_timeout', 180)
    # [可配置] - 已迁移到 config/agent_params.yaml
    IDLE_TIMEOUT_SECONDS = get_config('agent.worker.idle_timeout', 300)
    # [可配置] - 已迁移到 config/agent_params.yaml
    ZOMBIE_HEARTBEAT_THRESHOLD = get_config('agent.worker.zombie_threshold', 90)

    def __init__(self, max_workers: int = 30, resource_tracker: ResourceTracker = None) -> None:
        self.max_workers = max_workers
        self._workers: Dict[str, WorkerAgent] = {}
        self._idle_workers: List[str] = []
        self._busy_workers: List[str] = []
        self._destroy_logs: List[DestroyLog] = []
        self._resource_tracker = resource_tracker or ResourceTracker()
        self._task_handlers: Dict[str, Callable] = {}
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

    @property
    def workers(self) -> Dict[str, WorkerAgent]:
        return self._workers

    @property
    def idle_workers(self) -> List[str]:
        return self._idle_workers

    @property
    def busy_workers(self) -> List[str]:
        return self._busy_workers

    @property
    def resource_tracker(self) -> ResourceTracker:
        return self._resource_tracker

    @property
    def destroy_logs(self) -> List[DestroyLog]:
        return self._destroy_logs

    def register_task_handler(self, task_type: str, handler: Callable) -> int:
        self._task_handlers[task_type] = handler

    def register_task_handlers(self, handlers: Dict[str, Callable]) -> int:
        self._task_handlers.update(handlers)

    def _get_memory_mb(self) -> float:
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    async def create_worker(self, capabilities: List[str] = None) -> WorkerAgent:
        async with self._lock:
            if len(self._workers) >= self.max_workers:
                raise RuntimeError(f"已达到最大Worker数量: {self.max_workers}")

            worker = WorkerAgent(capabilities=capabilities)
            worker.start()

            self._create_worker_impl(worker)

            for task_type, handler in self._task_handlers.items():
                worker.register_handler(task_type, handler)

            self._workers[worker.worker_id] = worker
            self._idle_workers.append(worker.worker_id)

            logger.info(f"创建Worker: {worker.worker_id}")
            return worker

    def _create_worker_impl(self, worker) -> None:
        try:
            from core.services.llm_service import get_client_pool
            pool = get_client_pool()
            client = pool.create_isolated_client(worker.worker_id)
            if client:
                worker.llm_client = client
                self._resource_tracker.register(worker.worker_id, "llm_client", client)
        except Exception as e:
            logger.warning(f"为Worker注入LLM客户端失败(异步): {e}")

    def sync_create_worker(self, capabilities: List[str] = None) -> WorkerAgent:
        with self._sync_lock:
            if len(self._workers) >= self.max_workers:
                raise RuntimeError(f"已达到最大Worker数量: {self.max_workers}")

            worker = WorkerAgent(capabilities=capabilities)
            worker.start()

            self._sync_create_worker_impl(worker)

            self._workers[worker.worker_id] = worker
            self._idle_workers.append(worker.worker_id)

            logger.info(f"创建Worker: {worker.worker_id}")
            return worker

    def _sync_create_worker_impl(self, worker) -> None:
        try:
            from core.services.llm_service import get_client_pool
            pool = get_client_pool()
            client = pool.create_isolated_client(worker.worker_id)
            if client:
                worker.llm_client = client
                self._resource_tracker.register(worker.worker_id, "llm_client", client)
                logger.info(f"为Worker {worker.worker_id} 注入独立LLM客户端")
        except Exception as e:
            logger.warning(f"为Worker注入LLM客户端失败: {e}")

    async def destroy_worker(self, worker_id: str, force: bool = False, reason: str = "") -> bool:
        result = await self._destroy_worker_impl(worker_id, force, reason)
        if result.get("status") == "not_found":
            return False
        if result.get("status") == "busy":
            logger.warning(f"Worker {worker_id} 正在忙碌，无法销毁（需force=True）")
            return False
        if result.get("report"):
            logger.info(result["report"])
        return result["value"]

    async def _destroy_worker_impl(self, worker_id, force, reason):
        async with self._lock:
            if worker_id not in self._workers:
                return {"status": "not_found"}

            worker = self._workers[worker_id]
            was_busy = worker.state == WorkerState.BUSY

            if was_busy and not force:
                return {"status": "busy"}

            mem_before = self._get_memory_mb()
            destroy_reason = self._stop_worker(worker, worker_id, was_busy, force, reason)
            released = self._resource_tracker.release_all(worker_id)
            report = None
            if released:
                report = self._resource_tracker.get_release_report(worker_id, released)

            self._cleanup_worker_refs(worker_id)
            self._log_destroy(worker_id, destroy_reason, was_busy, mem_before, released)
            return {"status": "ok", "report": report, "value": True}

    def _stop_worker(self, worker, worker_id: str, was_busy: bool, force: bool, reason: str) -> str:
        if was_busy and force:
            worker.force_stop()
            destroy_reason = reason or f"强制销毁: BUSY超时(>{self.BUSY_TIMEOUT_SECONDS}s)或手动强制"
            logger.warning(f"[强制销毁] Worker {worker_id}: {destroy_reason}")
        else:
            worker.stop()
            destroy_reason = reason or "正常销毁"
        return destroy_reason

    def _cleanup_worker_refs(self, worker_id: str) -> None:
        del self._workers[worker_id]
        if worker_id in self._idle_workers:
            self._idle_workers.remove(worker_id)
        if worker_id in self._busy_workers:
            self._busy_workers.remove(worker_id)
        gc.collect()

    def _log_destroy(self, worker_id: str, destroy_reason: str, was_busy: bool, mem_before: float, released) -> None:
        self._log_destroy_impl(worker_id, destroy_reason, was_busy, mem_before, released)

    def _log_destroy_impl(self, worker_id: str, destroy_reason: str, was_busy: bool, mem_before: float, released) -> None:
        mem_after = self._get_memory_mb()
        log_entry = DestroyLog(
            worker_id=worker_id,
            reason=destroy_reason,
            was_busy=was_busy,
            memory_before_mb=round(mem_before, 1),
            memory_after_mb=round(mem_after, 1),
            resources_released=released,
        )
        self._destroy_logs.append(log_entry)

    def sync_destroy_worker(self, worker_id: str, force: bool = False, reason: str = "") -> bool:
        result = self._sync_destroy_worker_impl(worker_id, force, reason)
        if result.get("status") == "not_found":
            return False
        if result.get("status") == "busy":
            logger.warning(f"Worker {worker_id} 正在忙碌，无法销毁（需force=True）")
            return False
        if result.get("report"):
            logger.info(result["report"])
        return result["value"]

    def _sync_destroy_worker_impl(self, worker_id, force, reason):
        with self._sync_lock:
            if worker_id not in self._workers:
                return {"status": "not_found"}

            worker = self._workers[worker_id]
            was_busy = worker.state == WorkerState.BUSY

            if was_busy and not force:
                return {"status": "busy"}

            mem_before = self._get_memory_mb()
            destroy_reason = self._stop_worker(worker, worker_id, was_busy, force, reason)

            released = self._resource_tracker.release_all(worker_id)
            report = None
            if released:
                report = self._resource_tracker.get_release_report(worker_id, released)

            self._cleanup_worker_refs(worker_id)
            self._log_destroy(worker_id, destroy_reason, was_busy, mem_before, released)
            return {"status": "ok", "report": report, "value": True}

    async def find_available_worker(self, task: Task) -> Optional[WorkerAgent]:
        for worker_id in self._idle_workers:
            worker = self._workers[worker_id]
            if worker.can_handle(task):
                return worker

        if len(self._workers) < self.max_workers:
            try:
                worker = await self.create_worker(capabilities=[task.task_type])
                return worker
            except Exception as e:
                logger.error(f"创建Worker失败: {e}")

        return None

    def mark_busy(self, worker_id: str) -> None:
        if worker_id in self._idle_workers:
            self._idle_workers.remove(worker_id)
        if worker_id not in self._busy_workers:
            self._busy_workers.append(worker_id)

    def mark_idle(self, worker_id: str) -> None:
        if worker_id in self._busy_workers:
            self._busy_workers.remove(worker_id)
        if worker_id not in self._idle_workers:
            self._idle_workers.append(worker_id)

    async def cleanup_idle_workers(self, max_idle_time: int = 300) -> int:
        cleaned = 0
        now = datetime.now()

        async with self._lock:
            to_remove = []

            for worker_id in self._idle_workers[:]:
                worker = self._workers.get(worker_id)
                if worker and worker.stats.last_task_at:
                    idle_time = (now - worker.stats.last_task_at).total_seconds()
                    if idle_time > max_idle_time:
                        to_remove.append(worker_id)

            for worker_id in to_remove:
                if await self.destroy_worker(worker_id):
                    cleaned += 1

        return cleaned

    async def cleanup_zombie_workers(self) -> int:
        cleaned = 0

        async with self._lock:
            to_force_destroy = []

            for worker_id in self._busy_workers[:]:
                worker = self._workers.get(worker_id)
                if worker and worker.is_zombie(threshold=self.ZOMBIE_HEARTBEAT_THRESHOLD):
                    busy_duration = worker.get_busy_duration()
                    heartbeat_age = worker.get_heartbeat_age()
                    to_force_destroy.append((worker_id, f"zombie_timeout: BUSY={busy_duration:.0f}s, heartbeat={heartbeat_age:.0f}s"))

            for worker_id, reason in to_force_destroy:
                if await self.destroy_worker(worker_id, force=True, reason=reason):
                    cleaned += 1
                    logger.warning(f"[僵尸清理] 强制销毁Worker {worker_id}: {reason}")

        if cleaned > 0:
            logger.info(f"[定期清理] 清理了{cleaned}个僵尸Worker")

        return cleaned

    def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        worker = self._workers.get(worker_id)
        if worker:
            return worker.get_status()
        return None

    def get_all_workers(self) -> List[Dict[str, Any]]:
        return [w.get_status() for w in self._workers.values()]

    def get_active_workers(self) -> List[str]:
        return list(self._workers.keys())

    def get_idle_worker_count(self) -> int:
        return len(self._idle_workers)

    def get_busy_worker_count(self) -> int:
        return len(self._busy_workers)
