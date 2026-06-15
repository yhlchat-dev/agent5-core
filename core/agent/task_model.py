"""
任务数据模型
定义任务相关的数据结构
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from core.utils.config_loader import get_config


class TaskStatus(Enum):
    """任务状态枚举"""
    # [枚举值] - 无需迁移
    PENDING = "pending"
    # [枚举值] - 无需迁移
    RUNNING = "running"
    # [枚举值] - 无需迁移
    COMPLETED = "completed"
    # [枚举值] - 无需迁移
    FAILED = "failed"
    # [枚举值] - 无需迁移
    CANCELLED = "cancelled"
    # [枚举值] - 无需迁移
    TIMEOUT = "timeout"


class TaskPriority(Enum):
    """任务优先级枚举"""
    # [枚举值] - 无需迁移
    LOW = 1
    # [枚举值] - 无需迁移
    NORMAL = 2
    # [枚举值] - 无需迁移
    HIGH = 3
    # [枚举值] - 无需迁移
    CRITICAL = 4


@dataclass
class Task:
    """
    任务数据类
    表示一个可执行的任务
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    task_type: str = "generic"
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    worker_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeout: int = get_config('global.limits.task_timeout', 120)
    retry_count: int = 0
    max_retries: int = get_config('global.limits.max_retries', 3)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "priority": self.priority.value,
            "status": self.status.value,
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
            "parent_id": self.parent_id,
            "children": self.children,
            "worker_id": self.worker_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """从字典创建"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            task_type=data.get("task_type", "generic"),
            priority=TaskPriority(data.get("priority", 2)),
            status=TaskStatus(data.get("status", "pending")),
            payload=data.get("payload", {}),
            result=data.get("result"),
            error=data.get("error"),
            parent_id=data.get("parent_id"),
            children=data.get("children", []),
            worker_id=data.get("worker_id"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            timeout=data.get("timeout", 120),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            metadata=data.get("metadata", {}),
        )
    
    def start(self, worker_id: str) -> None:
        """开始任务"""
        self.status = TaskStatus.RUNNING
        self.worker_id = worker_id
        self.started_at = datetime.now()
    
    def complete(self, result: Any = None) -> None:
        """完成任务"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()
    
    def fail(self, error: str) -> None:
        """任务失败"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
    
    def cancel(self) -> None:
        """取消任务"""
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()
    
    def timeout_task(self) -> None:
        """任务超时"""
        self.status = TaskStatus.TIMEOUT
        self.error = "任务超时"
        self.completed_at = datetime.now()
    
    def can_retry(self) -> bool:
        """是否可以重试"""
        return self.retry_count < self.max_retries
    
    def increment_retry(self) -> None:
        """增加重试计数"""
        self.retry_count += 1
        self.status = TaskStatus.PENDING
    
    def is_finished(self) -> bool:
        """是否已完成"""
        return self.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT
        ]
    
    def get_duration(self) -> Optional[float]:
        """获取执行时长（秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration": self.duration,
            "metadata": self.metadata,
        }
