# -*- coding: utf-8 -*-
"""
SharedRuntimeContext — 全局运行时上下文

所有核心实例的唯一来源。
禁止在模块内部 new GeneLibrary/GeneCommitLayer/PlannerV2/GoalGenerator。
所有模块通过 runtime_context.xxx 获取共享实例。

Phase 8.3.2: Runtime Activation Repair
"""
import logging
from typing import Any, Optional


class SharedRuntimeContext:
    """全局运行时上下文

    核心原则：
    - 禁止在模块内部 new GeneLibrary/GeneCommitLayer/PlannerV2/GoalGenerator
    - 所有模块通过 runtime_context.xxx 获取共享实例
    - 初始化顺序由 SharedRuntimeContext 保证
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("SharedRuntimeContext")

        # 核心数据层
        self.gene_library: Any = None
        self.gene_commit_layer: Any = None
        self.gene_mutation_budget: Any = None
        self.gene_snapshot_manager: Any = None

        # 治理层
        self.weight_allocator: Any = None
        self.drift_controller: Any = None
        self.gene_governance_hub: Any = None
        self.self_evolving_governance_hub: Any = None

        # 认知层
        self.planner: Any = None
        self.goal_generator: Any = None

        # 记忆层
        self.bridge_memory: Any = None

        # 观测层
        self.observation_hub: Any = None

        # 模式学习层
        self.pattern_registry: Any = None
        self.pattern_reward_engine: Any = None
        self.pattern_evolution_engine: Any = None

        # Constitution 层
        self.constitution_runtime: Any = None

        # Motivation 层
        self.motivation_runtime: Any = None

        # Personality 层
        self.personality_kernel: Any = None
        self.personality_hook: Any = None
        self.identity_core: Any = None

        # Value System 层
        self.value_runtime: Any = None

        # Identity Recovery 层
        self.identity_recovery: Any = None

        # Identity Distance 层
        self.identity_distance: Any = None

        # Trajectory Drift 层
        self.trajectory_drift_detector: Any = None

        # Gene Sandbox 层
        self.gene_sandbox: Any = None

        # Unified Reward 层
        self.unified_reward_layer: Any = None
        self.reward_trace: Any = None

        # Memory Runtime 层
        self.memory_runtime: Any = None

        # Governor Hook 层
        self.governor_hook: Any = None

    def initialize(self) -> None:
        """初始化所有核心实例

        初始化顺序：
        1. GeneLibrary (数据层)
        2. GeneMutationBudget + GeneSnapshotManager (支撑层)
        3. GeneCommitLayer (写入层)
        4. WeightAllocator + DriftController (治理层)
        5. GeneGovernanceHub + SelfEvolvingGovernanceHub (治理入口)
        6. CuriosityGoalGenerator (认知层)
        7. BridgeMemory (记忆层)
        """
        from core.strategy_os.genome.gene_library import GeneLibrary
        from core.strategy_os.genome.gene_mutation_budget import GeneMutationBudget
        from core.strategy_os.genome.gene_snapshot_manager import GeneSnapshotManager
        from core.strategy_os.genome.gene_commit_layer import GeneCommitLayer
        from core.observation.analytics.gene_governance.gene_weight_allocator import GeneWeightAllocator
        from core.observation.analytics.gene_governance.gene_drift_controller import GeneDriftController
        from core.observation.analytics.gene_governance.gene_governance_hub import GeneGovernanceHub
        from core.observation.analytics.gene_governance_v3.self_evolving_governance_hub import SelfEvolvingGovernanceHub
        from core.cognition.curiosity_goal_generator import CuriosityGoalGenerator
        from core.value_system.bridge_memory import BridgeMemory

        # 1. 数据层
        self.gene_library = GeneLibrary(allow_runtime_write=False)

        # 2. 支撑层
        self.gene_mutation_budget = GeneMutationBudget()
        self.gene_snapshot_manager = GeneSnapshotManager()

        # 3. 写入层
        self.gene_commit_layer = GeneCommitLayer(
            gene_library=self.gene_library,
            mutation_budget=self.gene_mutation_budget,
            snapshot_manager=self.gene_snapshot_manager,
        )

        # 4. 治理层
        self.weight_allocator = GeneWeightAllocator()
        self.drift_controller = GeneDriftController()

        # 5. 治理入口
        self.gene_governance_hub = GeneGovernanceHub()
        self.self_evolving_governance_hub = SelfEvolvingGovernanceHub()

        # 6. 认知层
        self.goal_generator = CuriosityGoalGenerator()

        # 7. 记忆层
        self.bridge_memory = BridgeMemory()

        # 8. 模式学习层
        from core.pattern_learning.pattern_registry import PatternRegistry
        from core.pattern_learning.pattern_reward_engine import PatternRewardEngine
        from core.pattern_learning.pattern_evolution_engine import PatternEvolutionEngine

        self.pattern_registry = PatternRegistry()
        self.pattern_reward_engine = PatternRewardEngine(registry=self.pattern_registry)
        self.pattern_evolution_engine = PatternEvolutionEngine(registry=self.pattern_registry)

        # 9. Constitution 层
        from core.constitution.constitution_runtime import ConstitutionRuntime
        self.constitution_runtime = ConstitutionRuntime()

        # 10. 重新绑定 PatternRewardEngine（接入 Constitution）
        self.pattern_reward_engine = PatternRewardEngine(
            registry=self.pattern_registry,
            constitution_runtime=self.constitution_runtime,
        )

        # 11. Motivation 层
        from core.motivation.motivation_runtime import MotivationRuntime
        self.motivation_runtime = MotivationRuntime()

        # 12. Personality 层
        from core.cognition.personality_kernel_v1.personality_kernel import PersonalityKernelV1
        from core.cognition.personality_kernel_v1.personality_runtime_hook import PersonalityRuntimeHook
        from core.cognition.identity_core import IdentityCore

        self.personality_kernel = PersonalityKernelV1()
        self.personality_hook = PersonalityRuntimeHook(self.personality_kernel)
        self.identity_core = IdentityCore()

        # 将 IdentityCore 的 values 注入 PersonalityKernel
        identity_values = self.identity_core.current_state.values
        self.personality_kernel.set_identity_vector(identity_values)

        # 13. Value System 层
        from core.value_system.value_runtime import ValueRuntime
        self.value_runtime = ValueRuntime()
        self.value_runtime.update_positive_from_identity(identity_values)

        # 15. Identity Distance 层
        from core.cognition.identity_distance_engine import IdentityDistanceEngine
        self.identity_distance = IdentityDistanceEngine()

        # 14. Identity Recovery 层 (依赖 identity_distance)
        from core.cognition.identity_recovery_controller import IdentityRecoveryController
        self.identity_recovery = IdentityRecoveryController(
            identity_core=self.identity_core,
            personality_kernel=self.personality_kernel,
            threshold=0.1,
            identity_distance=self.identity_distance,
        )
        self.identity_recovery.set_anchor()

        # 16. Trajectory Drift 层
        from core.cognition.trajectory_drift_detector import TrajectoryDriftDetector
        self.trajectory_drift_detector = TrajectoryDriftDetector()

        # 17. Gene Sandbox 层
        from core.gene_runtime.gene_sandbox import GeneSandbox
        self.gene_sandbox = GeneSandbox()

        # 18. Unified Reward 层
        from core.reward_system.unified_reward_layer import UnifiedRewardLayer
        from core.reward_system.reward_trace import RewardTrace
        self.reward_trace = RewardTrace()
        self.unified_reward_layer = UnifiedRewardLayer(trace=self.reward_trace)

        # 19. Memory Runtime 层
        from core.memory_runtime.memory_runtime import MemoryRuntime
        self.memory_runtime = MemoryRuntime(bridge_memory=self.bridge_memory)

        # 20. Governor Hook 层
        from core.cognition.constitution_governor.constitution_governor import ConstitutionGovernor
        from core.cognition.constitution_governor.governor_runtime_hook import GovernorRuntimeHook

        identity_values = (
            dict(self.identity_core.current_state.values)
            if self.identity_core
            else {}
        )
        self.governor_hook = GovernorRuntimeHook(
            ConstitutionGovernor(
                identity_values=identity_values
            )
        )

        # 预计算 PSI，使第一个 cycle 即可走快速路径
        self.governor_hook.governor.compute_psi(
            identity_alignment=0.8,
            curiosity_health=0.8,
            gene_stability=0.8,
            governance_consistency=0.8,
        )

        self.logger.info("[SharedRuntimeContext] initialized: all core instances created")

    def register_planner(self, planner: Any) -> None:
        """注册 PlannerV2 实例（由 CognitiveController 创建后注册）"""
        self.planner = planner
        self.logger.info("[SharedRuntimeContext] planner registered")

    def register_observation_hub(self, hub: Any) -> None:
        """注册 ObservationHub 实例"""
        self.observation_hub = hub
        self.logger.info("[SharedRuntimeContext] observation_hub registered")

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self.gene_library is not None


# 全局单例
_global_context: Optional[SharedRuntimeContext] = None


def get_runtime_context() -> SharedRuntimeContext:
    """获取全局 SharedRuntimeContext 单例"""
    global _global_context
    if _global_context is None:
        _global_context = SharedRuntimeContext()
        _global_context.initialize()
    return _global_context


def reset_runtime_context() -> None:
    """重置全局上下文（仅用于测试）"""
    global _global_context
    _global_context = None
