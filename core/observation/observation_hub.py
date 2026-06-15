# -*- coding: utf-8 -*-
"""
ObservationHub — 统一观测入口

所有 logger 统一挂载入口，提供一站式观测 API。
纯观测，不参与决策。

Phase 7.6.5: 挂载 CausalGraphBuilder + CausalQueryAPI
Phase 8.1: 挂载 GeneGovernanceHub V2 + SelfEvolvingGovernanceHub V3
"""
import logging
from typing import Any, Dict, List, Optional

from core.observation.event_bus import EventBus, get_event_bus, ON_EPISODE_END
from core.observation.reward_logger import RewardLogger
from core.observation.constitution_trace import ConstitutionTraceLogger
from core.observation.curiosity_tracker import CuriosityTracker
from core.observation.sanity_monitor import SanityMonitor
from core.observation.violation_map import ViolationMap
from core.observation.trajectory_recorder import TrajectoryRecorder
from core.observation.analytics.causal.causal_graph_builder import CausalGraphBuilder, CausalGraph
from core.observation.analytics.causal.causal_query_api import CausalQueryAPI
from core.observation.analytics.gene_governance.gene_governance_hub import GeneGovernanceHub, GeneGovernanceState
from core.observation.analytics.gene_governance_v3.self_evolving_governance_hub import SelfEvolvingGovernanceHub, GovernanceSystemState


class ObservationHub:
    """统一观测入口

    所有 logger 统一挂载到同一个 EventBus。
    提供一站式观测 API。

    Phase 7.6.5: 新增 CausalGraphBuilder + CausalQueryAPI
    Phase 8.1: 新增 GeneGovernanceHub V2 + SelfEvolvingGovernanceHub V3
    Phase 8.3: V2 WeightAllocation → GeneUpdateProposal → CommitQueue（禁止直接写 GeneLibrary）
    Phase 8.4: PolicyVector 注入到 GeneSelector / WeightAllocator / DriftController / GoalSystem / Planner
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus or get_event_bus()
        self.logger = logging.getLogger("ObservationHub")

        # 挂载所有 logger
        self._reward_logger = RewardLogger(self._event_bus)
        self._constitution_logger = ConstitutionTraceLogger(self._event_bus)
        self._curiosity_tracker = CuriosityTracker(self._event_bus)
        self._sanity_monitor = SanityMonitor(self._event_bus)
        self._violation_map = ViolationMap(self._event_bus)
        self._trajectory_recorder = TrajectoryRecorder(self._event_bus)

        # Phase 7.6.5: 挂载 CausalGraphBuilder + CausalQueryAPI
        self._causal_graph_builder = CausalGraphBuilder()
        self._causal_query_api = CausalQueryAPI()
        self._causal_graphs: List[CausalGraph] = []

        # Phase 8.1: 挂载 Governance V2 + V3
        self._gene_governance_hub = GeneGovernanceHub()
        self._self_evolving_governance_hub = SelfEvolvingGovernanceHub()
        self._governance_v2_states: List[GeneGovernanceState] = []
        self._governance_v3_states: List[GovernanceSystemState] = []
        self._prev_drift_score: float = 0.0  # 用于计算 gene_stability_change

        # Phase 8.3.2: 使用 SharedRuntimeContext 的共享实例
        self._commit_queue = None
        self._proposal_reviewer = None
        self._gene_commit_layer = None
        self._gene_library = None
        try:
            from core.runtime.shared_runtime_context import get_runtime_context
            _ctx = get_runtime_context()
            self._gene_library = _ctx.gene_library
            self._gene_commit_layer = _ctx.gene_commit_layer
        except Exception:
            pass
        try:
            from core.value_system.commit_queue import CommitQueue
            from core.value_system.proposal_reviewer import ProposalReviewer
            self._commit_queue = CommitQueue()
            self._proposal_reviewer = ProposalReviewer()
        except Exception:
            pass

        # 订阅 episode_end 事件，自动同步到 CausalGraphBuilder + Governance
        self._event_bus.subscribe(ON_EPISODE_END, self._on_episode_end)

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def reward_logger(self) -> RewardLogger:
        return self._reward_logger

    @property
    def constitution_logger(self) -> ConstitutionTraceLogger:
        return self._constitution_logger

    @property
    def curiosity_tracker(self) -> CuriosityTracker:
        return self._curiosity_tracker

    @property
    def sanity_monitor(self) -> SanityMonitor:
        return self._sanity_monitor

    @property
    def violation_map(self) -> ViolationMap:
        return self._violation_map

    @property
    def trajectory_recorder(self) -> TrajectoryRecorder:
        return self._trajectory_recorder

    @property
    def causal_graph_builder(self) -> CausalGraphBuilder:
        """Phase 7.6.5: 因果图构建器"""
        return self._causal_graph_builder

    @property
    def causal_query_api(self) -> CausalQueryAPI:
        """Phase 7.6.5: 因果查询 API"""
        return self._causal_query_api

    @property
    def causal_graphs(self) -> List[CausalGraph]:
        """Phase 7.6.5: 已构建的因果图列表"""
        return self._causal_graphs

    @property
    def gene_governance_hub(self) -> GeneGovernanceHub:
        """Phase 8.1: Gene 治理统一入口 V2"""
        return self._gene_governance_hub

    @property
    def self_evolving_governance_hub(self) -> SelfEvolvingGovernanceHub:
        """Phase 8.1: 自进化治理统一入口 V3"""
        return self._self_evolving_governance_hub

    @property
    def governance_v2_states(self) -> List[GeneGovernanceState]:
        """Phase 8.1: V2 治理状态历史"""
        return self._governance_v2_states

    @property
    def governance_v3_states(self) -> List[GovernanceSystemState]:
        """Phase 8.1: V3 治理状态历史"""
        return self._governance_v3_states

    def _on_episode_end(self, event) -> None:
        """Phase 7.6.5 + Phase 8.1: episode 结束时自动构建因果图 + 治理分析

        数据流:
        TrajectoryRecorder → CausalGraphBuilder → GeneGovernanceHub V2 → SelfEvolvingGovernanceHub V3

        注意：TrajectoryRecorder._on_episode_end 会先执行（先注册先执行），
        将 _current_episode 移入 _episodes，所以这里用 replay_episode(-1)。
        """
        try:
            episode_data = self._trajectory_recorder.replay_episode(-1)
            if not episode_data:
                return

            # === Phase 7.6.5: 构建因果图 ===
            graph = self._causal_graph_builder.build_from_episode(episode_data)
            self._causal_graphs.append(graph)
            ep_idx = len(self._causal_graphs) - 1
            self._causal_query_api.load_episode(ep_idx, episode_data)

            # === Phase 8.1: Governance V2 接线 ===
            self._run_governance_v2(episode_data)

            # === Phase 8.1: Governance V3 接线 ===
            self._run_governance_v3()

        except Exception:
            pass

    def _run_governance_v2(self, episode_data: List[Dict[str, Any]]) -> None:
        """Phase 8.1: Governance V2 接线

        Trajectory → GeneInfluenceEstimator → MediationBalancer → WeightAllocator → DriftController
        """
        try:
            # 将 TrajectoryStep 嵌套结构展平为 Estimator 期望的扁平结构
            # TrajectoryStep.to_dict() = {step, state: {gene_id, curiosity_score, ...}, action, reward, ...}
            # Estimator 期望 = {gene_id, reward, curiosity_score, goal_type, ...}
            flat_episodes = []
            all_raw = self._trajectory_recorder.export_all()
            for ep in all_raw:
                flat_ep = []
                for step in ep:
                    flat = dict(step.get("state", {}))
                    flat["reward"] = step.get("reward", 0.0)
                    flat["step"] = step.get("step", 0)
                    flat_ep.append(flat)
                flat_episodes.append(flat_ep)
            if not flat_episodes:
                # fallback: 用当前 episode_data
                flat_ep = []
                for step in episode_data:
                    flat = dict(step.get("state", {}))
                    flat["reward"] = step.get("reward", 0.0)
                    flat["step"] = step.get("step", 0)
                    flat_ep.append(flat)
                flat_episodes = [flat_ep]

            # 提取出现的 gene_id 列表
            gene_ids = list(set(
                step.get("gene_id", "") for ep in flat_episodes for step in ep if step.get("gene_id", "")
            ))
            if not gene_ids:
                gene_ids = ["default_gene"]

            # 1. 获取 gene 影响力状态
            for gid in gene_ids:
                state = self._gene_governance_hub.get_gene_influence_state(gid, flat_episodes)

                # 2. 从 InfluenceVector 提取指标，应用治理控制
                if state.influence_vector and state.influence_vector.total > 0:
                    causal_strength = state.influence_vector.normalized_gene_power
                    mediated = state.influence_vector.mediated_curiosity + state.influence_vector.mediated_goal
                    mediation_ratio = mediated / state.influence_vector.total if state.influence_vector.total > 0 else 0.0
                else:
                    causal_strength = 0.0
                    mediation_ratio = 0.0

                # stability_score: 从 WeightAllocator 历史推导（首次用默认值 0.5）
                stability_score = 0.5
                if self._governance_v2_states:
                    last_state = self._governance_v2_states[-1]
                    if last_state.weight_allocation:
                        stability_score = 1.0 - abs(last_state.weight_allocation.updated_weight - 1.0)

                # 应用治理控制（current_fitness=None → 跳过 drift 检测）
                control_state = self._gene_governance_hub.apply_governance_control(
                    gene_id=gid,
                    causal_strength=causal_strength,
                    mediation_ratio=mediation_ratio,
                    stability_score=stability_score,
                    current_fitness=None,
                )
                self._governance_v2_states.append(control_state)

                # 记录 drift_score 用于 V3 的 gene_stability_change
                if control_state.drift_result:
                    self._prev_drift_score = control_state.drift_result.drift_score

                # Phase 8.3: WeightAllocation → GeneUpdateProposal → CommitQueue
                # 禁止直接写 GeneLibrary，只产生提案推送 CommitQueue
                if (control_state.weight_allocation
                        and self._commit_queue and self._proposal_reviewer):
                    wa = control_state.weight_allocation
                    # 权重变化映射为 fitness_delta
                    weight_delta = wa.updated_weight - wa.original_weight
                    fitness_delta = weight_delta * 0.1  # 缩放因子，避免过大变化
                    if abs(fitness_delta) > 0.001:
                        from core.value_system.models.gene_update_proposal import GeneUpdateProposal
                        proposal = GeneUpdateProposal(
                            gene_id=gid,
                            current_fitness=0.5,  # 占位，CommitLayer 会读取真实值
                            fitness_delta=fitness_delta,
                            proposed_fitness=0.5 + fitness_delta,
                            confidence=causal_strength,
                            reason=f"governance_v2: weight {wa.original_weight:.3f}→{wa.updated_weight:.3f}, {wa.adjustment_reason}",
                            source="governance_v2",
                        )
                        # Reviewer 审核
                        decision = self._proposal_reviewer.review(proposal)
                        if decision.decision == "ACCEPT":
                            self._commit_queue.add(proposal)

                # Phase 8.4 接线 A: WeightAllocation → GeneSelector
                # 将 governance_weights 注入 GeneSelector（通过全局属性）
                # 实际注入由外部调用 inject_governance_weights 完成

                # Phase 8.4 接线 B: DriftControlResult → ExecutionPolicy
                # FREEZE/AMPLIFY/DECAY 通过 GeneCommitLayer 执行
                if control_state.drift_result and self._gene_commit_layer:
                    drift = control_state.drift_result
                    if drift.control_action == "FREEZE":
                        # FREEZE: 不执行任何 fitness 变更，仅记录
                        self.logger.info(
                            f"[ObservationHub] DRIFT FREEZE: gene_id={gid}, "
                            f"drift_score={drift.drift_score:.3f}"
                        )
                    elif drift.control_action == "DECAY":
                        # DECAY: fitness *= 0.95
                        self._gene_commit_layer.commit(
                            gene_id=gid,
                            fitness_delta=-0.05 * drift.current_fitness if drift.current_fitness else -0.025,
                            source="drift_control",
                            reason=f"drift DECAY: {drift.reason}",
                        )
                    elif drift.control_action == "AMPLIFY":
                        # AMPLIFY: fitness *= 1.05
                        self._gene_commit_layer.commit(
                            gene_id=gid,
                            fitness_delta=0.05 * drift.current_fitness if drift.current_fitness else 0.025,
                            source="drift_control",
                            reason=f"drift AMPLIFY: {drift.reason}",
                        )
        except Exception:
            pass

    def _run_governance_v3(self) -> None:
        """Phase 8.1: Governance V3 接线

        RewardLogger + CuriosityTracker + V2 状态 → PolicyOptimizer → DriftDetector
        """
        try:
            # 从 RewardLogger 获取 reward_mean_change
            reward_mean_change = self._reward_logger.get_mean_change()

            # 从 CuriosityTracker 获取 curiosity 指标
            curiosity_entropy_change = self._curiosity_tracker.get_entropy_change()
            exploration_entropy = self._curiosity_tracker.get_entropy()

            # 从 V2 DriftController 获取 gene_stability_change / gene_instability
            gene_stability_change = 0.0
            gene_instability = 0.0
            if self._governance_v2_states:
                last_v2 = self._governance_v2_states[-1]
                if last_v2.drift_result:
                    gene_instability = last_v2.drift_result.drift_score
                    gene_stability_change = gene_instability - self._prev_drift_score

            # 从 V2 WeightAllocator 统计 suppression_ratio
            suppression_ratio = 0.0
            v2_summary = self._gene_governance_hub.get_system_summary()
            weight_stats = v2_summary.get("weight_stats", {})
            total_genes = weight_stats.get("gene_count", 0)
            if total_genes > 0:
                all_weights = self._gene_governance_hub.weight_allocator.get_all_weights()
                suppressed = sum(1 for w in all_weights.values() if w < 0.5)
                suppression_ratio = suppressed / total_genes

            # 调用 V3 update_governance_policy
            v3_state = self._self_evolving_governance_hub.update_governance_policy(
                reward_mean_change=reward_mean_change,
                curiosity_entropy_change=curiosity_entropy_change,
                gene_stability_change=gene_stability_change,
                exploration_entropy=exploration_entropy,
                gene_instability=gene_instability,
                suppression_ratio=suppression_ratio,
                stability_index=0.5,
            )
            self._governance_v3_states.append(v3_state)

            # Phase 8.3.2: PolicyVector → Runtime 注入
            if v3_state.current_policy:
                policy = v3_state.current_policy
                # 接线 C: PolicyVector → WeightAllocator + DriftController
                self._gene_governance_hub.weight_allocator.inject_policy(policy)
                self._gene_governance_hub.drift_controller.inject_policy(policy)

                # 接线 D: PolicyVector → Planner (通过 SharedRuntimeContext)
                try:
                    from core.runtime.shared_runtime_context import get_runtime_context
                    _ctx = get_runtime_context()
                    if _ctx.planner is not None:
                        _ctx.planner.inject_policy(policy)
                except Exception:
                    pass

                # 接线 E: PolicyVector → GoalGenerator (通过 SharedRuntimeContext)
                try:
                    from core.runtime.shared_runtime_context import get_runtime_context
                    _ctx = get_runtime_context()
                    if _ctx.goal_generator is not None:
                        # 计算 suppression_ratio
                        suppression_ratio = 0.0
                        v2_summary = self._gene_governance_hub.get_system_summary()
                        weight_stats = v2_summary.get("weight_stats", {})
                        total_genes = weight_stats.get("gene_count", 0)
                        if total_genes > 0:
                            all_weights = self._gene_governance_hub.weight_allocator.get_all_weights()
                            suppressed = sum(1 for w in all_weights.values() if w < 0.5)
                            suppression_ratio = suppressed / total_genes
                        _ctx.goal_generator.inject_policy(policy, suppression_ratio)
                except Exception:
                    pass

                # 记录注入事件
                self.logger.info(
                    f"[ObservationHub] PolicyVector injected: "
                    f"alpha={policy.mediation_alpha:.2f}, "
                    f"decay={policy.gene_decay_factor:.2f}, "
                    f"amp={policy.gene_amplification_factor:.2f}, "
                    f"drift_t={policy.drift_threshold:.2f}"
                )
        except Exception:
            pass

    @property
    def gene_commit_layer(self):
        """Phase 8.4: 获取 GeneCommitLayer 实例"""
        return self._gene_commit_layer

    def get_full_report(self) -> Dict[str, Any]:
        """获取完整观测报告"""
        report = {
            "reward": self._reward_logger.get_stats(),
            "constitution": self._constitution_logger.get_stats(),
            "curiosity": self._curiosity_tracker.get_stats(),
            "sanity": self._sanity_monitor.get_stats(),
            "violations": self._violation_map.get_stats(),
            "trajectory": self._trajectory_recorder.get_stats(),
            "event_bus": self._event_bus.get_stats(),
        }
        # Phase 7.6.5: 因果图统计
        if self._causal_graphs:
            report["causal"] = {
                "graph_count": len(self._causal_graphs),
                "total_nodes": sum(g.node_count for g in self._causal_graphs),
                "total_edges": sum(g.edge_count for g in self._causal_graphs),
            }
        # Phase 8.1: Governance V2/V3 统计
        report["governance_v2"] = self._gene_governance_hub.get_system_summary()
        report["governance_v3"] = self._self_evolving_governance_hub.get_system_summary()
        return report

    def answer_questions(self) -> Dict[str, Any]:
        """回答验收标准的 5 个问题"""
        curiosity_state = self._curiosity_tracker.get_current_state()
        reward_dist = self._reward_logger.log_distribution()
        constitution_summary = self._constitution_logger.get_rule_impact_summary()

        return {
            "1_reward_变化": reward_dist,
            "2_constitution_影响": constitution_summary,
            "3_curiosity_是否稳定": curiosity_state,
            "4_是否出现_collapse": curiosity_state.get("state") == "collapse",
            "5_每一步发生了什么": self._trajectory_recorder.replay_current(),
        }


# 全局单例
_global_hub: Optional[ObservationHub] = None


def get_observation_hub() -> ObservationHub:
    """获取全局 ObservationHub 单例"""
    global _global_hub
    if _global_hub is None:
        _global_hub = ObservationHub()
    return _global_hub
