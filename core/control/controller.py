# -*- coding: utf-8 -*-
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from core.utils.logger import get_logger
from core.self.self_state import SelfState
from core.self.regulator import Regulator
from core.self.persona import Persona
from core.control.planner.task_graph import TaskGraph

from core.control.strategy_scheduler import StrategyScheduler
from core.control.memory_coordinator import MemoryCoordinator
from core.control.perception_integrator import PerceptionIntegrator
from core.control.intent_parser import IntentParser
from core.control.evolution_manager import EvolutionManager


@dataclass
class ControllerInitContext:
    module_switch: Any
    llm_service: Any = None
    task_queue: Any = None
    scheduler: Any = None
    kernel: Any = None


class Controller:

    def __init__(self, module_switch: Any, llm_service: Optional[Any] = None, task_queue: Optional[Any] = None, scheduler: Optional[Any] = None, kernel: Optional[Any] = None) -> None:
        self._init_with_context(ControllerInitContext(
            module_switch=module_switch, llm_service=llm_service,
            task_queue=task_queue, scheduler=scheduler, kernel=kernel
        ))

    def _init_with_context(self, ctx: ControllerInitContext) -> None:
        self.module_switch = ctx.module_switch
        self.kernel = ctx.kernel
        self.task_queue = ctx.task_queue
        self._last_decision = None
        self._last_graph: TaskGraph = None
        self._adaptive_limits = None
        self.runtime_policy = {}
        self.logger = get_logger("Controller")

        # 1. Memory (no cross-domain dependencies)
        self.memory = MemoryCoordinator()

        # 2. Perception (no cross-domain dependencies)
        self.perception = PerceptionIntegrator()

        # 3. Strategy/Scheduling (needs memory objects for Coordinator)
        self.strategy = StrategyScheduler(
            module_switch=ctx.module_switch,
            llm_service=ctx.llm_service,
            kernel=ctx.kernel,
            full_storage=self.memory.full_storage,
            raw_event_store=self.memory.raw_event_store,
            timeline=self.memory.timeline,
            index_manager=self.memory.index_manager,
            task_queue=self.task_queue,
            logger=self.logger,
        )

        # 4. Intent (needs memory objects)
        self.intent = IntentParser(
            strategy_memory=self.memory.strategy_memory,
            long_term_memory=self.memory.long_term_memory,
            experience_buffer=self.memory.experience_buffer,
        )

        # 5. Evolution (needs memory + strategy objects)
        self.evolution = EvolutionManager(
            strategy_memory=self.memory.strategy_memory,
            experience_buffer=self.memory.experience_buffer,
            long_term_memory=self.memory.long_term_memory,
            strategy_manager=self.strategy.strategy_manager,
            experience_manager=self.memory.experience_manager,
            timeline=self.memory.timeline,
            evolution_timeline=self.memory.evolution_timeline,
            logger=self.logger,
        )

        # Wire policy engine (needs learning_loop from evolution)
        self.strategy.init_policy(
            learning_memory=self.memory.learning_memory,
            strategy_memory=self.memory.strategy_memory,
            learning_loop=self.evolution.learning_loop,
        )

        # Override scheduler if provided
        if ctx.scheduler:
            self.strategy.scheduler = ctx.scheduler
        self.scheduler = self.strategy.scheduler

        # Self
        self.self_state = SelfState()
        self.regulator = Regulator()
        self.persona = Persona()

        # Backward-compatible attribute aliases
        self._setup_aliases()

    def _setup_aliases(self) -> None:
        # Planning
        self.planner = self.strategy.planner
        self.conflict_resolver = self.strategy.conflict_resolver
        self.resource_scheduler = self.strategy.resource_scheduler
        self.resource_monitor = self.strategy.resource_monitor
        self.task_monitor = self.strategy.task_monitor
        self.state_manager = self.strategy.state_manager

        # Strategy / orchestration
        self.strategy_manager = self.strategy.strategy_manager
        self.policy_engine = self.strategy.policy_engine
        self.coordinator = self.strategy.coordinator
        self.task_dispatcher = self.strategy.task_dispatcher
        self.task_tracker = self.strategy.task_tracker
        self.execution_tracer = self.strategy.execution_tracer
        self.performance_monitor = self.strategy.performance_monitor

        # Memory
        self.learning_memory = self.memory.learning_memory
        self.experience_buffer = self.memory.experience_buffer
        self.long_term_memory = self.memory.long_term_memory
        self.strategy_memory = self.memory.strategy_memory
        self.full_storage = self.memory.full_storage
        self.raw_event_store = self.memory.raw_event_store
        self.index_manager = self.memory.index_manager
        self.experience_extractor = self.memory.experience_extractor
        self.temp_memory = self.memory.temp_memory
        self.context_buffer = self.memory.context_buffer
        self.task_context_manager = self.memory.task_context_manager
        self.task_type_detector = self.memory.task_type_detector
        self.task_time_policy = self.memory.task_time_policy
        self.time_decay = self.memory.time_decay
        self.recency_filter = self.memory.recency_filter
        self.context_validator = self.memory.context_validator
        self.memory_policy_engine = self.memory.memory_policy_engine
        self.timeline = self.memory.timeline
        self.evolution_timeline = self.memory.evolution_timeline
        self.experience_manager = self.memory.experience_manager
        self.experience_evolver = self.memory.experience_evolver

        # Perception
        self.perception_fusion = self.perception.perception_fusion

        # Intent
        self.intent_resolver = self.intent.intent_resolver
        self.intent_confidence = self.intent.intent_confidence
        self.clarification_engine = self.intent.clarification_engine
        self.prompt_manager = self.intent.prompt_manager

        # Evolution / learning
        self.feedback_analyzer = self.evolution.feedback_analyzer
        self.pattern_extractor = self.evolution.pattern_extractor
        self.strategy_updater = self.evolution.strategy_updater
        self.learning_loop = self.evolution.learning_loop
        self.strategy_evolution = self.evolution.strategy_evolution
        self.performance_analyzer = self.evolution.performance_analyzer
        self.evolution_trigger = self.evolution.evolution_trigger
        self.human_request_gateway = self.evolution.human_request_gateway
        self.hybrid_replay_engine = self.evolution.hybrid_replay_engine
        self.strategy_learner = self.evolution.strategy_learner
        self.evolution_scheduler = self.evolution.evolution_scheduler

    def decide(self, state: Dict[str, Any]) -> TaskGraph:
        graph = self.strategy.decide(state)
        self._last_graph = graph
        return graph

    def decide_and_enqueue(self, state: Dict[str, Any]) -> None:
        self.strategy.decide_and_enqueue(state)

    def feedback(self, task: Any, result: Any) -> None:
        status = result.get("status")

        self.task_monitor.record(task, result)

        task_type = task.get("type") if isinstance(task, dict) else getattr(task, "type", None)
        success = status == "success" or status == "done"

        self.memory.add_feedback_event(task, result, self._last_decision)

        if success and task_type:
            self.memory.store_experience(task, self._last_decision, 1.0)
        elif task_type:
            self.memory.store_experience(task, self._last_decision, 0.0)

        if self._last_decision:
            self.memory.record_learning(task, self._last_decision, result)

        action = self._last_decision.get("action", "unknown") if self._last_decision else "unknown"

        self.evolution.record_and_update(
            task_type=task_type,
            action=action,
            success=success,
            resources=self._get_resources(),
        )

        self.evolution.try_evolution(task, success, self.timeline)

        if status == "failed":
            self.handle_failure(task, result)
        elif status == "blocked":
            self.handle_blocked(task, result)
        else:
            self.handle_success(task, result)

    def handle_failure(self, task: Any, result: Any) -> None:
        self.strategy.handle_failure(task, result)

    def handle_blocked(self, task: Any, result: Any) -> None:
        self.strategy.handle_blocked(task, result)

    def handle_success(self, task: Any, result: Any) -> None:
        self.strategy.handle_success(task, result)

    def replan(self, state: Dict[str, Any]) -> TaskGraph:
        graph = self.strategy.replan(state, self._last_graph)
        self._last_graph = graph
        return graph

    def get_graph(self) -> TaskGraph:
        return self._last_graph

    def get_resource_health(self) -> Dict[str, Any]:
        return self.strategy.get_resource_health()

    def get_task_stats(self) -> Dict[str, Any]:
        return self.strategy.get_task_stats()

    def decide_with_policy(self, task: Any) -> Dict[str, Any]:
        if self.kernel and hasattr(self.kernel, 'route_task'):
            return self.kernel.route_task(task)

        self._refresh_adaptive_limits()

        payload = task.get('payload', {}) if isinstance(task, dict) else {}
        if payload.get('force_execute') == True:
            return {
                'action': 'execute',
                'priority': 10,
                'reason': 'force_execute_override',
                'task': task
            }

        self._update_self_state()

        intent = self.intent.parse_task(task)
        if not self.intent.is_confident(intent.confidence):
            decision = self.intent.handle_low_confidence(task, intent, self.logger)
            if decision is not None:
                self._last_decision = decision
                return decision

        state = self._build_decision_state(task, intent)
        decision = self.policy_engine.decide(state)
        decision = self.strategy.apply_pattern_bias(state, decision, intent)
        self._last_decision = decision
        self.strategy.dispatch_decision(task, decision)
        return decision

    def _refresh_adaptive_limits(self) -> None:
        try:
            from core.control.adaptive_limits import get_adaptive_limits
            al = get_adaptive_limits()
            al.refresh()
            self._adaptive_limits = al
        except Exception:
            pass

    def _build_decision_state(self, task: Any, intent: Any) -> Dict[str, Any]:
        self_state = self.self_state.get()
        self.runtime_policy = self.regulator.adjust(self_state)

        task_dict = task if isinstance(task, dict) else {
            "type": getattr(task, "type", None),
            "description": getattr(task, "description", ""),
            "priority": getattr(task, "priority", 5),
            "retry": getattr(task, "retry_count", 0),
        }

        state = {
            "task": task_dict,
            "queue_size": self.task_queue.size() if self.task_queue else 0,
            "resources": self._get_resources(),
            "runtime_policy": self.runtime_policy,
            "intent": intent.to_dict(),
        }

        if self.prompt_manager:
            prompt_ctx = self.intent.build_context(intent.intent_type.value, intent)
            state["prompt_context"] = prompt_ctx

        time_aware_strategy = self._time_aware_decision(task_dict)
        if time_aware_strategy:
            state["time_aware_strategy"] = time_aware_strategy

        task_type_category = self.memory.detect_task_type(task_dict)
        if task_type_category != "normal":
            state["task_time_category"] = task_type_category

        return state

    def _update_self_state(self) -> None:
        queue_size = self.task_queue.size() if self.task_queue else 0
        stats = self.task_monitor.get_stats()
        success_rate = stats.get("success_rate", 1.0)
        self.self_state.update_from_system(queue_size, success_rate)

    def _get_resources(self) -> Dict[str, Any]:
        return self.perception.get_resources(self._adaptive_limits)

    def _time_aware_decision(self, task: Any) -> Optional[Dict[str, Any]]:
        task_type = task.get("type") if isinstance(task, dict) else getattr(task, "type", None)
        if not task_type:
            return None

        if self.memory.consecutive_failures(n=3):
            self.evolution.evolve_from_timeline(self.timeline)
            return {"action": "explore_new", "reason": "consecutive_failures"}

        if self.memory.consecutive_successes(n=3):
            return {"action": "reinforce", "reason": "consecutive_successes"}

        stale = self.evolution.get_stale_types_for_exploration()
        if task_type in stale:
            return {"action": "explore", "reason": "stale_type"}

        experiences = self.memory.get_valid_experience(task)
        if not experiences:
            return {"action": "explore", "reason": "no_valid_experience"}

        best = experiences[0]
        correctness = best["evaluation"].get("correctness", 0.5)
        if correctness < 0.4:
            return {"action": "explore", "reason": "low_correctness"}

        best_strategy = best.get("strategy", {})
        if isinstance(best_strategy, dict) and best_strategy.get("action"):
            return {"action": "reuse", "strategy": best_strategy["action"], "reason": "valid_experience"}

        return None

    def trigger_idle_evolution(self) -> Dict[str, Any]:
        self.evolution.trigger_idle_evolution()

    def get_evolution_status(self) -> Dict[str, Any]:
        return self.evolution.get_evolution_status()

    def request_human_input(self, question: str, context: Dict[str, Any]) -> Any:
        return self.evolution.request_human_input(question, context)
