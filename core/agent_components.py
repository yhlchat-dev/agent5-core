import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from config.run_mode import is_cognitive_only
from config.module_registry import should_enable_module
from core.utils.config_loader import ConfigLoader
from core.utils.logger import get_logger
from core.utils.data_initializer import initialize_data_dirs

from core.memory_system.memory_manager import MemoryManager
from core.perception.perception_manager import PerceptionManager
from core.safety.safety_manager import SafetyManager
from core.agent.agent_manager import AgentManager
from core.agent.master_agent import MasterAgent
from core.cognition import CuriositySystem
from core.task_planner import TaskPlanner
from core.critic import Critic
from core.goals.goal_generator import GoalGenerator
from core.perception.snapshot_engine.webpage_capture import WebpageCapture
from core.perception.interpreter.prompt_builder import PromptBuilder
from core.perception.interpreter.llm_bridge import LLMBridge
from core.safety.output_guard import OutputGuard
from core.safety.identity_guard import IdentityGuard
from core.safety.intent_guard import IntentGuard
from core.safety.consistency_lock import ConsistencyLock
from core.safety.module_switch import ModuleSwitch
from core.control.task_queue import TaskQueue
from core.control.scheduler import Scheduler
from core.control.feedback_router import FeedbackRouter
from core.control.controller import Controller
from core.perception.state_builder import StateBuilder
from core.perception.semantic_state_builder import SemanticStateBuilder
from core.perception.context_memory_builder import ContextMemoryBuilder
from core.execution.v2.step_planner import StepPlanner
from core.capsule.capsule_registry import CapsuleRegistry
from core.capsule.capsule_manager import CapsuleManager
from core.execution.v2.step_executor import StepExecutor
from core.execution.v2.recovery_manager import RecoveryManager
from core.evolution.self_evolution_engine import SelfEvolutionEngine
from core.safety.agent_guard import AgentGuard
from core.agent.sub_agent import SubAgent
from core.execution.v2.execution_engine import ExecutionEngineV2
from core.llm.llm_client import LLMClient
from core.llm.llm_switch import LLMSwitch


@dataclass
class AgentComponentBundle:
    memory_manager: Any = None
    perception_manager: Any = None
    safety_manager: Any = None
    agent_manager: Any = None
    master_agent: Any = None
    curiosity_system: Any = None
    task_planner: Any = None
    critic: Any = None
    goal_generator: Any = None
    llm_bridge: Any = None
    identity_core: Any = None
    teacher_integration: Any = None
    curiosity_engine_v3: Any = None
    self_evolution_loop: Any = None
    memory_bridge: Any = None
    capsule_manager: Any = None
    modify_guard: Any = None
    backup_manager: Any = None
    rollback_manager: Any = None
    output_guard: Any = None
    identity_guard: Any = None
    intent_guard: Any = None
    consistency_lock: Any = None
    module_switch: Any = None
    task_queue: Any = None
    scheduler: Any = None
    feedback_router: Any = None
    controller: Any = None
    execution_engine: Any = None
    llm_client: Any = None
    safety_os: Any = None
    golden_chain_manager: Any = None
    webpage_capture: Any = None
    ui_module: Dict[str, Any] = field(default_factory=dict)
    ui_manager: Any = None
    module_hub: Any = None
    observation_hub: Any = None
    runtime_context: Any = None  # Phase 8.3.2: SharedRuntimeContext


@dataclass
class CreateAgentLayerContext:
    config_loader: Any
    logger: Any
    memory_mgr: Any
    safety_mgr: Any
    kernel: Any


class AgentComponentFactory:
    @staticmethod
    def create_all(config_loader: ConfigLoader, logger: logging.Logger, ui_mode: str, kernel: Any = None) -> AgentComponentBundle:
        initialize_data_dirs()
        bundle = AgentComponentBundle()

        # Phase 8.3.2: SharedRuntimeContext 最先初始化
        from core.runtime.shared_runtime_context import get_runtime_context
        bundle.runtime_context = get_runtime_context()
        logger.info("SharedRuntimeContext 初始化完成")

        bundle.memory_manager, bundle.memory_bridge, bundle.capsule_manager = AgentComponentFactory._create_memory_layer(config_loader, logger)
        bundle.perception_manager = AgentComponentFactory._create_perception_layer(config_loader, logger)
        bundle.safety_manager, bundle.output_guard, bundle.identity_guard, bundle.intent_guard, bundle.consistency_lock = AgentComponentFactory._create_safety_layer(config_loader, logger)
        bundle.agent_manager, bundle.master_agent, bundle.module_hub = AgentComponentFactory._create_agent_layer(config_loader, logger, bundle.memory_manager, bundle.safety_manager, kernel)
        bundle.curiosity_system, bundle.identity_core, bundle.teacher_integration, bundle.curiosity_engine_v3, bundle.self_evolution_loop = AgentComponentFactory._create_cognition_layer(logger, bundle.memory_manager)
        bundle.task_planner, bundle.critic, bundle.goal_generator, bundle.execution_engine, bundle.controller = AgentComponentFactory._create_execution_layer(config_loader, logger)
        bundle.llm_bridge, bundle.llm_client = AgentComponentFactory._create_llm_layer(logger)
        bundle.safety_os, bundle.golden_chain_manager = AgentComponentFactory._create_safety_os_layer(logger)
        bundle.webpage_capture = WebpageCapture()
        bundle.ui_module, bundle.ui_manager = AgentComponentFactory._create_ui_module(ui_mode, logger)

        if bundle.master_agent is not None:
            # Phase 7.5 Runtime Activation: 使用 ObservationHub 替代旧 observation_init
            from core.observation.observation_hub import ObservationHub
            from core.observation.event_bus import EventBus
            obs_bus = EventBus()
            bundle.observation_hub = ObservationHub(obs_bus)
            bundle.master_agent.set_observation_hub(bundle.observation_hub)
            logger.info("观测系统初始化完成 (ObservationHub + EventBus)")

        return bundle

    @staticmethod
    def _create_memory_layer(config_loader: ConfigLoader, logger: logging.Logger):
        memory_manager = MemoryManager(config_loader)
        logger.info("记忆管理器初始化完成")

        from core.memory_system.memory_bridge import get_memory_bridge
        from core.memory_system.capsules.capsule_manager import get_capsule_manager
        from core.safety.modify_guard import get_modify_guard
        from core.safety.backup_manager import get_backup_manager
        from core.safety.rollback_manager import get_rollback_manager

        memory_bridge = get_memory_bridge()
        logger.info("记忆桥接层初始化完成")

        capsule_manager = get_capsule_manager()
        logger.info("胶囊管理器初始化完成")

        return memory_manager, memory_bridge, capsule_manager

    @staticmethod
    def _create_perception_layer(config_loader: ConfigLoader, logger: logging.Logger):
        return AgentComponentFactory._create_perception_layer_impl(config_loader)

    @staticmethod
    def _create_perception_layer_impl(config_loader: ConfigLoader):
        return PerceptionManager(config_loader)

    @staticmethod
    def _create_safety_layer(config_loader: ConfigLoader, logger: logging.Logger):
        safety_manager, output_guard, identity_guard, intent_guard, consistency_lock = AgentComponentFactory._create_safety_layer_impl(config_loader)
        logger.info("安全管理器初始化完成")
        logger.info("安全守卫(输出+身份+意图+一致性)初始化完成")
        return safety_manager, output_guard, identity_guard, intent_guard, consistency_lock

    @staticmethod
    def _create_safety_layer_impl(config_loader: ConfigLoader):
        safety_manager = SafetyManager(config_loader)
        output_guard = OutputGuard()
        identity_guard = IdentityGuard()
        intent_guard = IntentGuard()
        consistency_lock = ConsistencyLock()
        return safety_manager, output_guard, identity_guard, intent_guard, consistency_lock
    @staticmethod
    def _create_agent_layer(config_loader: ConfigLoader, logger: logging.Logger, memory_mgr, safety_mgr, kernel):
        ctx = CreateAgentLayerContext(config_loader=config_loader, logger=logger, memory_mgr=memory_mgr, safety_mgr=safety_mgr, kernel=kernel)
        return AgentComponentFactory._create_agent_layer_with_context(ctx)

    @staticmethod
    def _init_module_hub(ctx) -> Optional[Any]:
        """初始化 ModuleController，失败返回 None"""
        try:
            from core.module_os import ModuleController
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "module_registry.yaml")
            hub = ModuleController(config_path=config_path)
            ctx.logger.info(f"ModuleController 初始化完成 (已注册 {len(hub.registry.list_names())} 个模块)")
            return hub
        except Exception as e:
            ctx.logger.warning(f"ModuleHub 初始化失败: {e}")
            return None

    @staticmethod
    def _create_agent_layer_with_context(ctx: CreateAgentLayerContext):

        agent_manager = AgentManager(ctx.config_loader)
        ctx.logger.info("Agent管理器初始化完成")

        module_hub = None
        master_agent = None

        if is_cognitive_only():
            ctx.logger.info("[COGNITIVE_ONLY] MasterAgent 已跳过")
        else:
            module_hub = AgentComponentFactory._init_module_hub(ctx)

            master_agent = MasterAgent(
                agent_manager=agent_manager,
                memory_manager=ctx.memory_mgr,
                safety_manager=ctx.safety_mgr,
                config_loader=ctx.config_loader,
                kernel=ctx.kernel,
            )
            ctx.logger.info("Master代理初始化完成")

        return agent_manager, master_agent, module_hub
    @staticmethod
    def _create_cognition_layer(logger: logging.Logger, memory_mgr):
        curiosity_system = None
        if should_enable_module("CuriosityEngine"):
            curiosity_system = CuriositySystem(
                curiosity_capsule=memory_mgr.curiosity_capsule,
                skill_capsule=memory_mgr.skill_cache_capsule,
                config_loader=ConfigLoader(),
            )
            logger.info("好奇心系统初始化完成")
        else:
            logger.info("[COGNITIVE_ONLY] 好奇心系统已跳过")

        from core.cognition.identity_core import get_identity_core
        identity_core = get_identity_core()
        logger.info(f"Identity核心初始化完成 (version={identity_core._version})")

        teacher_integration = None
        if should_enable_module("TeachingSystem"):
            from core.cognition.teacher_integration import get_teacher_integration
            teacher_integration = get_teacher_integration()
            logger.info("Teacher集成系统初始化完成")
        else:
            logger.info("[COGNITIVE_ONLY] Teacher集成系统已跳过")

        curiosity_engine_v3 = None
        if should_enable_module("CuriosityEngine"):
            from core.cognition.curiosity_engine_v3 import get_curiosity_engine_v3
            curiosity_engine_v3 = get_curiosity_engine_v3()
            logger.info("Curiosity引擎V3初始化完成")
        else:
            logger.info("[COGNITIVE_ONLY] Curiosity引擎V3已跳过")

        self_evolution_loop = None
        if should_enable_module("SelfEvolutionLoop"):
            from core.cognition.self_evolution_loop import get_self_evolution_loop
            self_evolution_loop = get_self_evolution_loop()
            logger.info("自进化循环初始化完成")
        else:
            logger.info("[COGNITIVE_ONLY] 自进化循环已跳过")

        return curiosity_system, identity_core, teacher_integration, curiosity_engine_v3, self_evolution_loop

    @staticmethod
    def _create_execution_layer(config_loader: ConfigLoader, logger: logging.Logger):
        task_planner = TaskPlanner()
        logger.info("任务规划器初始化完成")

        critic = Critic()
        logger.info("评估器初始化完成")

        goal_generator = GoalGenerator()
        logger.info("目标生成器初始化完成")

        module_switch = ModuleSwitch()
        task_queue = TaskQueue()
        scheduler = Scheduler()
        feedback_router = FeedbackRouter()
        controller = Controller(module_switch, task_queue=task_queue, scheduler=scheduler)

        state_builder = StateBuilder()
        semantic_state_builder = SemanticStateBuilder()
        context_memory_builder = ContextMemoryBuilder()
        step_planner = StepPlanner()
        capsule_registry = CapsuleRegistry()
        capsule_exec_manager = CapsuleManager(capsule_registry)
        step_executor = StepExecutor(capsule_manager=capsule_exec_manager)
        recovery_manager = RecoveryManager()
        evolution_engine = SelfEvolutionEngine()
        agent_guard = AgentGuard()
        sub_agent = SubAgent(guard=agent_guard, capsule_manager=capsule_exec_manager)

        execution_engine = ExecutionEngineV2(
            step_planner, step_executor, recovery_manager,
            evolution_engine=evolution_engine,
            agent_guard=agent_guard,
            feedback_router=feedback_router,
            controller=controller,
        )
        logger.info("执行引擎初始化完成")

        return task_planner, critic, goal_generator, execution_engine, controller

    @staticmethod
    def _create_llm_layer(logger: logging.Logger):
        llm_bridge, llm_client = AgentComponentFactory._create_llm_layer_impl()
        logger.info("LLM桥接器初始化完成")
        logger.info("LLM客户端初始化完成")
        return llm_bridge, llm_client

    @staticmethod
    def _create_llm_layer_impl():
        llm_bridge = LLMBridge()
        llm_switch = LLMSwitch(mode="safe")
        llm_client = LLMClient(switch=llm_switch)
        return llm_bridge, llm_client

    @staticmethod
    def _create_safety_os_layer(logger: logging.Logger):
        safety_os, golden_chain_manager, golden_error = AgentComponentFactory._create_safety_os_layer_impl()
        logger.info("SafetyOS 初始化完成")
        if golden_error is not None:
            logger.warning(f"黄金数据链管理器初始化失败: {golden_error}")
        elif golden_chain_manager is not None:
            logger.info("黄金数据链管理器初始化完成")
        return safety_os, golden_chain_manager

    @staticmethod
    def _create_safety_os_layer_impl():
        from core.safety.safety_os import SafetyOS
        from core.timeline.timeline_manager import TimelineManager
        from core.causal.causal_engine import CausalEngine
        from core.safety.learning.safety_learner import SafetyLearner

        _tm = TimelineManager(max_size=2000)
        _ce = CausalEngine()
        _learner = SafetyLearner()
        # 绑定 EventStore 持久化
        try:
            from core.cognitive_os.event_store import EventStore
            _es = EventStore()
            _tm.bind_event_store(_es)
        except Exception:
            pass
        safety_os = SafetyOS(timeline_manager=_tm, causal_engine=_ce, learner=_learner)

        golden_chain_manager = None
        golden_error = None
        try:
            from core.memory_system.capsules.golden_data_chain_capsule import GoldenDataChainManager
            golden_chain_manager = GoldenDataChainManager()
        except Exception as e:
            golden_error = e

        return safety_os, golden_chain_manager, golden_error

    @staticmethod
    def _create_ui_module(ui_mode: str, logger: logging.Logger):
        ui_module = {}
        ui_manager = None

        if ui_mode == "tkinter":
            from ui import (
                MainChatWindow, FloatMonitorWindow,
                check_dependencies, print_dependency_status,
                GLOBAL_STATE, data_provider,
            )
            ui_module = {
                'MainChatWindow': MainChatWindow,
                'FloatMonitorWindow': FloatMonitorWindow,
                'check_dependencies': check_dependencies,
                'print_dependency_status': print_dependency_status,
                'GLOBAL_STATE': GLOBAL_STATE,
                'data_provider': data_provider,
            }
            logger.info("Tkinter桌面面板初始化完成")
        else:
            from interfaces.ui_manager import UIManager
            ui_manager = UIManager()
            logger.info("PyQt5 UI管理器初始化完成")

        return ui_module, ui_manager
