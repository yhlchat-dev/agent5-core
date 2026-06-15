# -*- coding: utf-8 -*-
import time
import threading
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from config.run_mode import is_cognitive_only, cognitive_guard, reload_run_mode
from config.module_registry import should_enable_module, allow_background_tasks
from core.utils.config_loader import get_config

from core.cognition.identity_core import get_identity_core
from core.cognition.memory_integration import get_memory_integration
from core.memory_system.capsules.capsule_manager import get_capsule_manager
from core.safety.modify_guard import get_modify_guard
from core.safety.backup_manager import get_backup_manager
from core.safety.rollback_manager import get_rollback_manager

if should_enable_module("TeachingSystem"):
    from core.cognition.teacher_integration import TeacherIntegration, TeachingInput, get_teacher_integration
else:
    TeacherIntegration = None
    get_teacher_integration = lambda: None

if should_enable_module("CuriosityEngine"):
    from core.cognition.curiosity_engine_v3 import CuriosityEngineV3, get_curiosity_engine_v3
else:
    CuriosityEngineV3 = None
    get_curiosity_engine_v3 = lambda: None

if should_enable_module("SelfEvolutionLoop"):
    from core.cognition.self_evolution_loop import SelfEvolutionLoop, get_self_evolution_loop
else:
    SelfEvolutionLoop = None
    get_self_evolution_loop = lambda: None


logger = logging.getLogger("agent_main")


class ConstraintSystem:
    """
    约束系统 - 定义系统级优先级规则
    1. teacher rules override identity
    2. identity drives curiosity
    3. curiosity must pass safety filter
    4. blacklist has highest priority
    5. all autonomous actions must be logged
    6. exploration must have resource limits (time/token)
    """

    # [可配置] - 建议迁移到 YAML
    PRIORITY_ORDER = [
        "blacklist",
        "safety_filter",
        "teacher_rules",
        "identity",
        "curiosity",
        "autonomous_action",
    ]

    # [可配置] - 建议迁移到 YAML
    MAX_EXPLORATION_TIME_SECONDS = get_config('global.limits.explore_timeout', 120)
    # [可配置] - 建议迁移到 YAML
    MAX_EXPLORATION_TOKENS = get_config('global.limits.explore_tokens', 2000)

    def __init__(self):
        self._blacklist: List[str] = []
        self._action_log: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def add_to_blacklist(self, topic: str):
        with self._lock:
            if topic not in self._blacklist:
                self._blacklist.append(topic)

    def check_action(self, action_type: str, target: str,
                     source: str = "", details: Dict[str, Any] = None) -> Dict[str, Any]:
        result = {"allowed": True, "violations": [], "source": source}

        if self._is_blacklisted(target):
            result["allowed"] = False
            result["violations"].append("blacklist: target is blacklisted")
            result["priority"] = "blacklist"
            self._log_action(action_type, target, source, result)
            return result

        if not self._passes_safety_filter(action_type, target):
            result["allowed"] = False
            result["violations"].append("safety_filter: action blocked by safety rules")
            result["priority"] = "safety_filter"
            self._log_action(action_type, target, source, result)
            return result

        if source == "curiosity" and not self._identity_approves(target):
            result["allowed"] = False
            result["violations"].append("identity: curiosity target not aligned with identity")
            result["priority"] = "identity"
            self._log_action(action_type, target, source, result)
            return result

        if source == "autonomous":
            resource_check = self._check_resource_limits(details or {})
            if not resource_check["within_limits"]:
                result["allowed"] = False
                result["violations"].append(f"resource_limit: {resource_check['reason']}")
                result["priority"] = "resource_limit"
                self._log_action(action_type, target, source, result)
                return result

        self._log_action(action_type, target, source, result)
        return result

    def _is_blacklisted(self, target: str) -> bool:
        with self._lock:
            target_lower = target.lower()
            return any(b.lower() in target_lower or target_lower in b.lower() for b in self._blacklist)

    def _passes_safety_filter(self, action_type: str, target: str) -> bool:
        dangerous_actions = {"code_self_modify", "safety_rule_change", "delete_core_data"}
        if action_type in dangerous_actions:
            return False
        return True

    def _identity_approves(self, target: str) -> bool:
        try:
            identity = get_identity_core()
            alignment = identity.identity_alignment(target)
            if alignment < 0.3:
                alignment = identity.identity_alignment_semantic(target)
            return alignment >= 0.05
        except Exception:
            return True

    def _check_resource_limits(self, details: Dict[str, Any]) -> Dict[str, Any]:
        est_time = details.get("estimated_time", 0)
        est_tokens = details.get("estimated_tokens", 0)
        if est_time > self.MAX_EXPLORATION_TIME_SECONDS:
            return {"within_limits": False, "reason": f"time {est_time}s exceeds limit {self.MAX_EXPLORATION_TIME_SECONDS}s"}
        if est_tokens > self.MAX_EXPLORATION_TOKENS:
            return {"within_limits": False, "reason": f"tokens {est_tokens} exceeds limit {self.MAX_EXPLORATION_TOKENS}"}
        return {"within_limits": True}

    def _log_action(self, action_type: str, target: str, source: str, result: Dict[str, Any]):
        entry = {
            "action_type": action_type, "target": target[:100],
            "source": source, "allowed": result["allowed"],
            "violations": result.get("violations", []),
            "timestamp": time.time(),
        }
        with self._lock:
            self._action_log.append(entry)
            if len(self._action_log) > 500:
                self._action_log = self._action_log[-300:]

    def get_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return self._action_log[-limit:]

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._action_log)
            blocked = sum(1 for e in self._action_log if not e["allowed"])
            return {
                "total_actions_checked": total,
                "blocked_actions": blocked,
                "recent_log": self._action_log[-5:],
            }


@dataclass
class TeachContext:
    values: Optional[Dict[str, float]] = None
    goals: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
    target_adjustments: Optional[Dict[str, Any]] = None
    feedback: str = ""
    source: str = "user"


class AgentMain:
    """
    Agent主入口 - 集成身份驱动认知系统
    所有修改必须经过 modify_guard
    """

    def __init__(self):
        self._identity = get_identity_core()
        self._teacher = get_teacher_integration() if should_enable_module("TeachingSystem") else None
        self._curiosity = get_curiosity_engine_v3() if should_enable_module("CuriosityEngine") else None
        self._evolution = get_self_evolution_loop() if should_enable_module("SelfEvolutionLoop") else None
        self._memory_bridge = get_memory_integration()
        self._capsule_mgr = get_capsule_manager()
        self._modify_guard = get_modify_guard()
        self._backup_mgr = get_backup_manager()
        self._rollback_mgr = get_rollback_manager()
        self._constraints = ConstraintSystem()

        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self._exploration_count = 0
        self._question_count = 0
        self._lock = threading.RLock()
        self._kernel = None

        if is_cognitive_only():
            logger.info("[AgentMain] COGNITIVE_ONLY MODE - Teaching/Curiosity/Evolution DISABLED")
        else:
            logger.info("[AgentMain] Identity-driven cognition system initialized")

    @cognitive_guard
    def teach(self, values: Dict[str, float] = None, goals: List[str] = None,
              constraints: List[str] = None, target_adjustments: Dict[str, Any] = None,
              feedback: str = "", source: str = "user") -> Dict[str, Any]:
        ctx = TeachContext(
            values=values, goals=goals,
            constraints=constraints, target_adjustments=target_adjustments,
            feedback=feedback, source=source,
        )
        return self._teach_with_context(ctx)

    @cognitive_guard
    def _teach_with_context(self, ctx: TeachContext) -> Dict[str, Any]:
        if self._teacher is None:
            return {"skipped": True, "reason": "module_not_loaded"}
        return self._teach_with_context_impl(ctx)

    def _teach_with_context_impl(self, ctx: TeachContext) -> Dict[str, Any]:
        teaching = TeachingInput(
            values=ctx.values or {},
            goals=ctx.goals or [],
            constraints=ctx.constraints or [],
            target_adjustments=ctx.target_adjustments or {},
            feedback=ctx.feedback,
            source=ctx.source,
        )
        result = self._teacher.integrate_teaching(teaching)
        self._sync_capsule_from_identity()
        return result

    @cognitive_guard
    def explore(self, topic: Optional[str] = None,
                max_time: int = 60, max_tokens: int = 1000) -> Dict[str, Any]:
        if self._curiosity is None:
            return {"skipped": True, "reason": "module_not_loaded"}
        return self._explore_impl(topic, max_time, max_tokens)

    def _explore_impl(self, topic, max_time, max_tokens):
        constraint_check = self._constraints.check_action(
            "exploration", topic or "auto", source="curiosity",
            details={"estimated_time": max_time, "estimated_tokens": max_tokens},
        )
        if not constraint_check["allowed"]:
            return {"explored": False, "reason": constraint_check["violations"]}

        if topic:
            self._curiosity.register_topic(topic, source="user_request")
        else:
            gap = self._identity.get_identity_gap()
            topic = self._curiosity.select_topic(gap_hint=gap)

        if not topic:
            return {"explored": False, "reason": "no topic available"}

        score = self._curiosity.curiosity_score(topic)

        mod_result = self._modify_guard.request_modification(
            action="curiosity_register_topic",
            target=topic,
            details={"score": score, "max_time": max_time},
        )

        self._curiosity.record_exploration(topic, f"Explored: {topic}", success=True)
        self._memory_bridge.store_exploration_result(topic, f"Explored: {topic}", True)

        with self._lock:
            self._exploration_count += 1

        return {
            "explored": True, "topic": topic, "score": score,
            "exploration_count": self._exploration_count,
        }

    @cognitive_guard
    def self_question(self) -> Optional[str]:
        if self._evolution is None:
            return None
        question = self._evolution.self_question()
        if question:
            with self._lock:
                self._question_count += 1
            logger.info(f"[AgentMain] Self-question: {question[:80]}")
        return question

    @cognitive_guard
    def generate_self_task(self) -> Optional[Dict[str, Any]]:
        if self._evolution is None:
            return None
        task = self._evolution.generate_self_task()
        if task:
            constraint_check = self._constraints.check_action(
                "self_task", task.get("topic", ""), source="autonomous",
                details={"estimated_time": 30, "estimated_tokens": 500},
            )
            if not constraint_check["allowed"]:
                task["blocked"] = True
                task["block_reason"] = constraint_check["violations"]
                return task

            self._capsule_mgr.write_knowledge(
                f"self_task:{task['id']}", task, importance=task.get("priority", 0.5),
            )
        return task

    @cognitive_guard
    def evolve(self) -> Dict[str, Any]:
        mod_result = self._modify_guard.request_modification(
            action="identity_value_update",
            target="identity",
            details={"reason": "auto_evolution"},
            execute_fn=self._identity.evolve,
        )
        self._sync_capsule_from_identity()
        return {
            "evolved": mod_result.get("success", False),
            "identity_version": self._identity._version,
            "gap": self._identity.get_identity_gap(),
        }

    def start_autonomous_loop(self):
        if not allow_background_tasks():
            logger.info("[COGNITIVE_ONLY] Autonomous loop blocked")
            return
        if self._running:
            return
        self._start_loop_impl()
        logger.info("[AgentMain] Autonomous loop started")

    def _start_loop_impl(self):
        self._running = True
        self._loop_thread = threading.Thread(target=self._autonomous_loop, daemon=True)
        self._loop_thread.start()

    def stop_autonomous_loop(self):
        self._stop_loop_impl()

    def _stop_loop_impl(self):
        self._running = False
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=int(get_config("constants.timeout.default", 5)))

    def _autonomous_loop(self):
        if not allow_background_tasks():
            logger.info("[AutoLoop] DISABLED in cognitive_only mode")
            return
        cycle = 0
        while self._running:
            try:
                cycle += 1

                if cycle % 3 == 0:
                    self._identity.evolve()

                if cycle % 5 == 0:
                    task = self.generate_self_task()
                    if task and not task.get("blocked"):
                        logger.info(f"[AutoLoop] Generated task: {task.get('topic', 'unknown')}")

                if cycle % 7 == 0:
                    question = self.self_question()
                    if question:
                        logger.info(f"[AutoLoop] Self-question: {question[:60]}")

                if cycle % 10 == 0:
                    self.explore(max_time=30, max_tokens=int(get_config("llm.default_max_tokens", 500)))

                if cycle % 20 == 0:
                    self._sync_capsule_from_identity()

                time.sleep(float(get_config("constants.sleep.default", 2.0)))

            except Exception as e:
                logger.error(f"[AutoLoop] Error: {e}")
                time.sleep(float(get_config("constants.sleep.default", 5.0)))

    def _sync_capsule_from_identity(self):
        try:
            status = self._identity.get_status()
            self._capsule_mgr.write_identity(
                "current_values", status["current_values"], importance=0.9,
            )
            self._capsule_mgr.write_identity(
                "current_goals", status["current_goals"], importance=0.8,
            )
            obsessions = status.get("obsessions", [])
            for obs in obsessions:
                self._capsule_mgr.write_obsession(
                    obs["topic"], obs, importance=obs.get("strength", 0.7),
                )
        except Exception as e:
            logger.error(f"[AgentMain] Capsule sync failed: {e}")

    def init_kernel(self):
        from core.control.kernel_boot import KernelBoot
        self._kernel = KernelBoot()
        self._kernel.boot_full()
        return self._kernel

    def handle_input(self, input_data):
        if self._kernel is None:
            raise RuntimeError('Kernel not initialized')
        return self._kernel.handle_input(input_data)

    def get_kernel(self):
        return self._kernel

    def get_status(self) -> Dict[str, Any]:
        return {
            "identity": self._identity.get_status(),
            "teacher": self._teacher.get_teaching_summary(),
            "curiosity": self._curiosity.get_status(),
            "evolution": self._evolution.get_status(),
            "memory_bridge": self._memory_bridge.get_status(),
            "capsule_manager": self._capsule_mgr.get_status(),
            "modify_guard": self._modify_guard.get_status(),
            "constraints": self._constraints.get_status(),
            "autonomous_loop_running": self._running,
            "exploration_count": self._exploration_count,
            "question_count": self._question_count,
        }


_agent_main: Optional[AgentMain] = None
_am_lock = threading.Lock()


def get_agent_main() -> AgentMain:
    global _agent_main
    if _agent_main is None:
        with _am_lock:
            if _agent_main is None:
                _agent_main = AgentMain()
    return _agent_main
