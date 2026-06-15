# -*- coding: utf-8 -*-
import logging
import random


from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class PlannerV2InitContext:
    llm_planner: Optional[Any] = None
    scorer: Optional[Any] = None
    filter_: Optional[Any] = None
    plan_memory: Optional[Any] = None
    plan_rl: Optional[Any] = None
    encoder: Optional[Any] = None
    strategy_graph: Optional[Any] = None
    graph_reasoner: Optional[Any] = None
    value_net: Optional[Any] = None
    value_encoder: Optional[Any] = None


class PlannerV2:

    def __init__(self, llm_planner: Optional[Any] = None, scorer: Optional[Any] = None, filter_: Optional[Any] = None, plan_memory: Optional[Any] = None, plan_rl: Optional[Any] = None, encoder: Optional[Any] = None, strategy_graph: Optional[Any] = None, graph_reasoner: Optional[Any] = None, value_net: Optional[Any] = None, value_encoder: Optional[Any] = None) -> None:
        ctx = PlannerV2InitContext(llm_planner=llm_planner, scorer=scorer, filter_=filter_, plan_memory=plan_memory, plan_rl=plan_rl, encoder=encoder, strategy_graph=strategy_graph, graph_reasoner=graph_reasoner, value_net=value_net, value_encoder=value_encoder)
        self._init_with_context(ctx)
        # Phase 8.4 接线 E: 可被 PolicyVector 覆盖
        self.search_depth: int = 5       # generate_candidates 的 k 值
        self.branch_factor: float = 1.0  # filter 宽松度乘数

    def inject_policy(self, policy) -> None:
        """Phase 8.4: 从 PolicyVector 注入参数

        - gene_amplification_factor 高 → search_depth 增加（更深入搜索）
        - mediation_alpha 高 → branch_factor 降低（更严格过滤）
        """
        # amplification_factor 1.0~2.0 → search_depth 3~8
        self.search_depth = int(3 + (policy.gene_amplification_factor - 1.0) * 10)
        self.search_depth = max(3, min(10, self.search_depth))
        # mediation_alpha 0.1~0.9 → branch_factor 1.2~0.6
        self.branch_factor = 1.2 - policy.mediation_alpha * 0.67

    def _init_with_context(self, ctx: PlannerV2InitContext) -> None:
        self.llm_planner = ctx.llm_planner
        self.scorer = ctx.scorer
        self.filter = ctx.filter_
        self.plan_memory = ctx.plan_memory
        self.plan_rl = ctx.plan_rl
        self.encoder = ctx.encoder
        self.strategy_graph = ctx.strategy_graph
        self.graph_reasoner = ctx.graph_reasoner
        self.value_net = ctx.value_net
        self.value_encoder = ctx.value_encoder
        self.logger = logging.getLogger("PlannerV2")

    def create_plan(self, state: Dict[str, Any], goal, prev_plan: Optional[Any] = None) -> None:
        candidates = self._generate_candidates(goal)

        if not candidates:
            self.logger.warning("[PlannerV2] no candidates generated")
            return None

        raw_count = len(candidates)

        filtered = self._filter_candidates(candidates, state)

        if not filtered:
            self.logger.warning("[PlannerV2] all candidates filtered out")
            return None

        best = self._select_best(state, filtered, prev_plan)

        if self.graph_reasoner is not None and prev_plan is not None:
            graph_best = self.graph_reasoner.find_best_next(prev_plan, filtered)
            if graph_best is not None:
                best = graph_best

        self.logger.info(
            f"[PlannerV2] selected best plan from "
            f"{raw_count} candidates ({len(filtered)} after filter)"
        )

        return best

    def _generate_candidates(self, goal) -> list:
        if self.llm_planner is not None:
            return self.llm_planner.generate_candidates(goal, k=self.search_depth)
        return []

    def _filter_candidates(self, candidates: list, state: Dict[str, Any]) -> None:
        if self.filter is not None:
            return self.filter.filter_with_fallback(candidates, state)
        return candidates

    def _select_best(self, state: Dict[str, Any], candidates: list, prev_plan: Optional[Any] = None) -> Any:
        if self.plan_rl is not None and self.plan_rl.should_explore():
            return random.choice(candidates)

        if self.scorer is not None and len(candidates) > 1:
            scored = []
            for p in candidates:
                base_score = self.scorer.score(state, p)

                rl_score = 0.0
                if self.plan_rl is not None and self.encoder is not None:
                    key = self.encoder.encode(state, p)
                    rl_score = self.plan_rl.get_q(key)

                graph_score = 0.5
                if self.strategy_graph is not None:
                    graph_score = self.strategy_graph.get_score(prev_plan, p)

                value_score = 0.0
                if self.value_net is not None and self.value_encoder is not None:
                    vec = self.value_encoder.encode(state, p)
                    value_score = self.value_net.predict(vec)

                final = (0.4 * base_score +
                         0.2 * rl_score +
                         0.2 * graph_score +
                         0.2 * value_score)
                scored.append((final, p))

            scored.sort(key=lambda x: -x[0])
            return scored[0][1]

        return candidates[0]
