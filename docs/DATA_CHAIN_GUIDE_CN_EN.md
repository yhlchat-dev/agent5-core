# Agent5 核心数据链路说明 / Agent5 Core Data Pipeline Guide

> 本文档说明已上传至 GitHub 的核心文件功能、模块划分、数据打通后的流程图及依赖关系。
> This document describes the functionality, module organization, data pipeline flow, and dependency relationships of the core files uploaded to GitHub.

---

## 目录 / Table of Contents

1. [模块总览 / Module Overview](#1-模块总览--module-overview)
2. [文件清单与功能 / File List & Functions](#2-文件清单与功能--file-list--functions)
3. [数据流程图 / Data Pipeline Flow](#3-数据流程图--data-pipeline-flow)
4. [依赖关系 / Dependencies](#4-依赖关系--dependencies)
5. [测试脚本 / Test Scripts](#5-测试脚本--test-scripts)
6. [配置文件 / Configuration Files](#6-配置文件--configuration-files)

---

## 1. 模块总览 / Module Overview

Agent5 系统由以下核心模块组成，数据链路已全部打通：

The Agent5 system consists of the following core modules, with all data pipelines fully connected:

| 模块 / Module | 路径 / Path | 功能 / Function |
|---|---|---|
| 系统入口 / System Entry | `main.py` | 应用层启动入口，黄金数据链完整流程 / Application entry, golden data chain full flow |
| Agent主入口 / Agent Entry | `core/agent_main.py` | Agent内核启动，约束系统 / Agent kernel boot, constraint system |
| 组件工厂 / Component Factory | `core/agent_components.py` | 40+模块组装中心 / 40+ module assembly center |
| Agent调度 / Agent Scheduling | `core/agent/` | Master/Sub/Worker Agent 任务调度 / Task scheduling |
| 记忆系统 / Memory System | `core/memory/` | 4层记忆架构(Working/Episodic/Semantic/Self) / 4-layer memory |
| LLM数据流 / LLM Pipeline | `core/llm/` | LLM调用+数据过滤+上下文构建 / LLM call + data filter + context build |
| 控制流 / Control Flow | `core/control/` | 决策控制+策略调度 / Decision control + strategy scheduling |
| 规划系统 / Planning | `core/planning/` | 目标规划+计划生成 / Goal planning + plan generation |
| 运行时 / Runtime | `core/runtime/` | 全局注册+执行引擎+协调器 / Global registry + execution engine + coordinator |
| 引导接线 / Bootstrap | `core/bootstrap/` | 依赖注入+系统构建 / Dependency injection + system building |
| 观测系统 / Observation | `core/observation/` | 事件总线+观测中枢+奖励解释 / Event bus + observation hub + reward explainer |
| 数据链 / Data Chain | `core/cognition/data_chain_v1.py` | 数据链V1生成器 / Data chain v1 generator |
| 身份系统 / Identity | `core/cognition/identity_core.py` | 统一身份内核 / Unified identity core |
| 安全系统 / Safety | `core/safety/` | SafetyOS审批+风险评估 / SafetyOS approval + risk evaluation |
| 时间线 / Timeline | `core/timeline/` | 事件时间线管理 / Event timeline management |
| 因果引擎 / Causal Engine | `core/causal_engine/` | 因果推理+因果图 / Causal reasoning + causal graph |
| 教师系统 / Teacher | `core/teacher/` | 因果判断+教师指导 / Causal judgment + teacher guidance |
| 价值真源 / Constitution | `core/constitution/` | 价值真源运行时 / Constitution runtime |
| 动机系统 / Motivation | `core/motivation/` | 动机运行时 / Motivation runtime |
| 价值系统 / Value System | `core/value_system/` | 价值运行时+价值向量 / Value runtime + value vector |
| 基因运行时 / Gene Runtime | `core/gene_runtime/` | 基因沙箱+进化 / Gene sandbox + evolution |
| 好奇心 / Curiosity | `core/cognition/curiosity_goal_generator.py` | 好奇心目标生成 / Curiosity goal generation |

---

## 2. 文件清单与功能 / File List & Functions

### 2.1 系统入口 / System Entry

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `main.py` | 系统主入口。启动AgentApplication，初始化所有组件，运行黄金数据链完整流程：`execute_with_golden_chain()` -> SafetyOS.approve() -> 执行 -> record_outcome() -> GoldenDataChainManager.create_chain()。/ Main entry. Boots AgentApplication, initializes all components, runs golden data chain full flow. |
| `core/agent_main.py` | Agent内核主入口。包含约束系统(ConstraintSystem)：blacklist -> safety_filter -> teacher_rules -> identity -> curiosity -> autonomous_action。通过 `init_kernel()` -> `KernelBoot().boot_full()` 启动完整内核。/ Agent kernel entry. Contains ConstraintSystem and kernel boot chain. |
| `core/agent_components.py` | 组件工厂。`AgentComponentFactory.create_all()` 按层初始化：SharedRuntimeContext -> Memory -> Perception -> Safety -> Agent -> Cognition -> Execution -> LLM -> SafetyOS -> UI。/ Component factory. Layer-by-layer initialization. |

### 2.2 Agent调度模块 / Agent Scheduling Modules

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/agent/master_agent.py` | MasterAgent Facade。用户输入 -> `decide_action()` -> 任务拆分 -> `submit_task()` -> AgentManager调度 -> Worker执行 -> `feedback()` 回调。通过EventBus发布on_step/on_reward/on_episode_end事件。/ MasterAgent Facade with task scheduling and event publishing. |
| `core/agent/sub_agent.py` | SubAgent。隐私标签检查链路：`_sanitize_params()` -> `get_label()` -> `check_data_access()` -> `sanitize_data()`。/ SubAgent with privacy label check chain. |
| `core/agent/worker_agent.py` | Worker。执行链路：`execute()` -> `_can_execute()` -> `_mark_busy()` -> `_execute_task()` -> `_mark_idle()`。支持心跳检测、僵尸检测、强制停止。/ Worker with execution, heartbeat and zombie detection. |
| `core/agent/agent_manager.py` | Agent管理器。`submit_task()` -> PriorityQueue -> `dispatch()` -> `find_available_worker()` -> `worker.execute()`。完整的Worker生命周期管理。/ Agent manager with priority queue and worker lifecycle. |
| `core/agent/task_model.py` | 核心数据模型：Task, TaskResult, TaskStatus, TaskPriority。支持`to_dict()`/`from_dict()`序列化。/ Core data models with serialization. |
| `core/agent/worker_pool.py` | Worker池。`create_worker()` -> LLM客户端注入 -> `register_task_handler()` -> `find_available_worker()`。/ Worker pool with LLM client injection. |
| `core/agent/sub_agent_pool.py` | SubAgent池。`add()`/`remove()`/`get_available()`/`get_least_loaded()`。/ SubAgent pool management. |

### 2.3 记忆系统 / Memory System

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/memory/memory_kernel.py` | 记忆系统核心。4层记忆：Working -> Episodic -> Semantic -> Self。数据流：`write()` -> `router.route()` -> `layer.store()`；`read()` -> 跨层`search()`。支持记忆提升`promote()`和衰减`decay_all()`。/ Memory kernel with 4-layer architecture, promote and decay. |
| `core/memory/memory_router.py` | 记忆路由。映射：raw_trace->working, short_term->episodic, pattern->semantic, identity->self。支持自定义路由注册和按重要性降级。/ Memory router with route mapping and importance-based fallback. |

### 2.4 LLM数据流 / LLM Pipeline

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/llm/llm_client.py` | LLM数据流核心。`call()` -> `builder.build()` -> `data_filter.filter()` -> `sanitizer.sanitize_dict()` -> `_call_llm()`。三模式切换：safe/balanced/full。/ LLM client with 3-mode switching and data filtering. |
| `core/llm/llm_switch.py` | LLM模式切换器。提供`is_safe_mode()`/`is_balanced_mode()`/`is_full_mode()`判断。/ LLM mode switch. |
| `core/llm/data_filter.py` | LLM数据过滤。safe模式只保留input/output，balanced保留input/output/summary，full全量透传。/ Data filter with mode-based field filtering. |
| `core/llm/context_builder.py` | LLM上下文构建。从task/result/memory构建LLM上下文字典。/ Context builder from task/result/memory. |

### 2.5 控制流 / Control Flow

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/control/controller.py` | 控制流核心。`decide()` -> `strategy.decide()` -> TaskGraph；`feedback()` -> `memory.add_feedback_event()` / `evolution.record_and_update()`。`decide_with_policy()`完整链路：intent解析 -> policy决策 -> strategy调度。/ Control core with strategy dispatch and policy engine. |

### 2.6 规划系统 / Planning

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/planning/planner.py` | 规划器。通过`bus.subscribe("goal.received")`订阅事件，收到目标后生成plan steps，`bus.emit("plan.created")`。/ Planner with event-driven plan generation. |
| `core/planning/planner_v2.py` | 规划器V2。增强版规划，支持更复杂的计划生成和评估。/ Enhanced planner with complex plan generation. |

### 2.7 运行时 / Runtime

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/runtime/global_registry.py` | 全局注册表。`register()`/`get()`/`register_factory()`，线程安全，支持延迟实例化。/ Global registry with thread safety and lazy instantiation. |
| `core/runtime/shared_runtime_context.py` | 20层运行时上下文。GeneLibrary -> GeneMutationBudget -> ... -> MemoryRuntime -> GovernorHook。所有核心实例通过`get_runtime_context()`全局单例获取。/ 20-layer runtime context with singleton pattern. |
| `core/runtime/unified_coordinator.py` | 统一协调器。`handle()` -> 路由判断 -> `_handle_controller_task()`/`_handle_routed_task()` -> `engine.execute()`。/ Unified coordinator with multi-coordinator routing. |
| `core/runtime/execution_engine.py` | 执行引擎。`execute()` -> `router.route(task)`。/ Execution engine with action routing. |
| `core/runtime/action_router.py` | 动作路由器。根据target/action路由到不同处理器。/ Action router with target/action dispatch. |
| `core/runtime/event_bus.py` | 运行时事件总线。发布-订阅模式，线程安全。/ Runtime event bus with pub-sub pattern. |

### 2.8 引导接线 / Bootstrap

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/bootstrap/wiring.py` | 依赖注入接线。`wire_all()` -> `wire_controller()`/`wire_agent()`/`wire_sub_agent()`/`wire_evolution()`。通过registry注入依赖关系。/ Dependency injection wiring through registry. |

### 2.9 观测系统 / Observation

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/observation/event_bus.py` | 事件总线。4种事件：on_step, on_reward, on_constitution_apply, on_episode_end。全局单例`get_event_bus()`。/ Event bus with 4 event types and global singleton. |
| `core/observation/observation_hub.py` | 统一观测入口。episode_end事件处理链：`trajectory_recorder.replay_episode()` -> `causal_graph_builder.build_from_episode()` -> `_run_governance_v2/v3()`。/ Unified observation hub with episode processing chain. |
| `core/observation/reward_explainer.py` | 奖励解释器。解释奖励信号的来源和原因。/ Reward explainer for reward signal interpretation. |

### 2.10 数据链与认知 / Data Chain & Cognition

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/cognition/data_chain_v1.py` | 数据链V1生成器。`DataChainContext`数据类 + `generate_data_chain_v1()`生成函数 + `save_data_chain_v1()`持久化。/ Data chain v1 generator with context, generation and persistence. |
| `core/cognition/identity_core.py` | 统一身份系统。维护Agent的身份状态和人格锚点。/ Unified identity system with persona anchor. |
| `core/cognition/curiosity_goal_generator.py` | 好奇心目标生成器。基于好奇心权重生成探索目标。/ Curiosity goal generator for exploration. |

### 2.11 安全系统 / Safety

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/safety/safety_os.py` | SafetyOS。`approve()` -> RiskEvaluator -> TripleTeacherSafetyAuditor -> 最终决策；`record_outcome()` -> SafetyLearner -> DataChainCapsule。/ SafetyOS with approval, triple teacher audit and outcome recording. |
| `core/safety/risk_evaluator.py` | 风险评估器。评估动作风险分数和置信度。/ Risk evaluator for action risk scoring. |

### 2.12 时间线与因果 / Timeline & Causal

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/timeline/timeline_manager.py` | 时间线管理器。记录和管理事件时间线。/ Timeline manager for event recording. |
| `core/causal_engine/causal_engine.py` | 因果引擎。因果推理和因果图构建。/ Causal engine for reasoning and graph building. |

### 2.13 教师系统 / Teacher

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/teacher/causal_judge.py` | 因果判断。基于因果推理判断动作的因果影响。/ Causal judgment based on causal reasoning. |
| `core/teacher/teacher_client.py` | 教师客户端。与教师系统交互获取指导。/ Teacher client for guidance interaction. |

### 2.14 认知运行时 / Cognitive Runtime

| 文件 / File | 功能描述 / Function Description |
|---|---|
| `core/constitution/constitution_runtime.py` | 价值真源运行时。维护Agent的核心价值约束。/ Constitution runtime for core value constraints. |
| `core/motivation/motivation_runtime.py` | 动机运行时。管理Agent的动机和驱动力。/ Motivation runtime for drives and motivation. |
| `core/value_system/value_runtime.py` | 价值运行时。管理正向/负向价值向量。/ Value runtime for positive/negative value vectors. |
| `core/value_system/value_vector.py` | 价值向量。正向价值向量的计算和更新。/ Value vector for positive value computation. |
| `core/gene_runtime/gene_sandbox.py` | 基因沙箱。安全的基因变异和进化环境。/ Gene sandbox for safe mutation and evolution. |

---

## 3. 数据流程图 / Data Pipeline Flow

### 3.1 主数据流 / Main Data Flow

```
用户输入 / User Input
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  main.py / AgentApplication                             │
│  AgentComponentFactory.create_all()                     │
│  ┌─────────────────────────────────────────────────┐    │
│  │ SharedRuntimeContext (20层初始化)                │    │
│  │ GeneLibrary -> GeneBudget -> GeneSnapshot ->    │    │
│  │ GeneCommit -> WeightAllocator -> DriftController │    │
│  │ -> GeneGovernance -> SelfEvolvingGovernance ->   │    │
│  │ CuriosityGoal -> BridgeMemory -> PatternRegistry │    │
│  │ -> ConstitutionRuntime -> MotivationRuntime ->   │    │
│  │ PersonalityKernel -> IdentityCore -> ValueRuntime │    │
│  │ -> IdentityDistance -> IdentityRecovery ->       │    │
│  │ TrajectoryDrift -> GeneSandbox -> UnifiedReward  │    │
│  │ -> MemoryRuntime -> GovernorHook                 │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  MasterAgent.decide_action()                            │
│  ├── TaskHandlers (任务处理)                            │
│  ├── SearchPlanning (搜索规划)                          │
│  └── EventBus.emit(on_step)                             │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  SafetyOS.approve(action_context)                       │
│  ├── RiskEvaluator.evaluate_risk() -> risk_score        │
│  ├── TripleTeacherSafetyAuditor.review()                │
│  │   ├── Planner Teacher (规划者视角)                   │
│  │   ├── Critic Teacher (批评者视角)                    │
│  │   └── CausalJudge (因果判断)                         │
│  └── _make_final_decision() -> allow/ask_human/block    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Controller.decide() / Controller.decide_with_policy()  │
│  ├── IntentParser.parse_task()                          │
│  ├── PolicyEngine.decide()                              │
│  ├── StrategyScheduler.apply_pattern_bias()             │
│  └── TaskGraph (任务图)                                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  AgentManager.submit_task()                             │
│  ├── PriorityQueue (优先级队列)                         │
│  ├── dispatch() -> find_available_worker()              │
│  └── WorkerAgent.execute()                              │
│      ├── _can_execute() -> _mark_busy()                 │
│      ├── _execute_task() (handler/timeout/cancel)       │
│      └── _mark_idle()                                   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  LLM数据流 / LLM Pipeline                              │
│  LLMClient.call()                                       │
│  ├── ContextBuilder.build() (上下文构建)                │
│  ├── DataFilter.filter() (数据过滤: safe/balanced/full) │
│  └── OutputSanitizer.sanitize() (输出净化)              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  结果反馈 / Result Feedback                             │
│  ├── SafetyOS.record_outcome()                          │
│  │   ├── SafetyLearner.record_feedback()                │
│  │   └── DataChainCapsuleManager.save_chain()           │
│  ├── MemoryKernel.write() (记忆写入)                    │
│  │   └── MemoryRouter.route() -> 4层记忆存储            │
│  ├── EventBus.emit(on_reward/on_episode_end)            │
│  └── ObservationHub._on_episode_end()                   │
│      ├── TrajectoryRecorder.replay_episode()            │
│      ├── CausalGraphBuilder.build_from_episode()        │
│      └── Governance V2/V3 (基因治理)                    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  黄金数据链 / Golden Data Chain                         │
│  GoldenDataChainManager.create_chain()                  │
│  ├── 1. Perception (感知层)                             │
│  ├── 2. Cognition (认知层: IdentityCore + Curiosity)    │
│  ├── 3. Memory Storage (记忆存储)                       │
│  ├── 4. Safety Audit (安全审计: SafetyOS决策)           │
│  ├── 5. Behavior Output (行为输出)                      │
│  └── 6. Self Growth (自我成长: Reward + Drift)          │
└─────────────────────────────────────────────────────────┘
```

### 3.2 内核启动流 / Kernel Boot Flow

```
agent_main.py -> init_kernel()
    │
    ▼
KernelBoot.boot_full()
    ├── _init_core_state()       (核心状态)
    ├── _init_clarification()    (澄清系统)
    ├── _init_module_os()        (模块操作系统)
    ├── _init_scheduler()        (调度器)
    ├── _init_memory_manager()   (记忆管理器)
    ├── _init_task_executor()    (任务执行器)
    ├── _init_memory_router()    (记忆路由)
    ├── _init_memory_os()        (记忆操作系统)
    ├── boot()                   (启动)
    └── _init_event_chain()      (认知链绑定)
        ├── Safety -> Decision
        ├── Memory -> Planning
        ├── Perception -> Execution
        └── Cognitive -> Observer -> Scheduler
```

### 3.3 认知循环 / Cognitive Cycle

```
observe -> constitution -> motivation -> goal -> planner -> pattern
    -> value_runtime -> behavior -> performance -> gene_commit
    -> identity_recovery
```

---

## 4. 依赖关系 / Dependencies

### 4.1 模块依赖图 / Module Dependency Graph

```
main.py
  ├── core/agent_components.py (组件工厂)
  │     ├── core/runtime/shared_runtime_context.py (运行时上下文)
  │     │     ├── core/gene_runtime/gene_sandbox.py
  │     │     ├── core/constitution/constitution_runtime.py
  │     │     ├── core/motivation/motivation_runtime.py
  │     │     ├── core/value_system/value_runtime.py
  │     │     ├── core/value_system/value_vector.py
  │     │     └── core/cognition/identity_core.py
  │     ├── core/memory/memory_kernel.py
  │     │     └── core/memory/memory_router.py
  │     ├── core/safety/safety_os.py
  │     │     ├── core/safety/risk_evaluator.py
  │     │     ├── core/timeline/timeline_manager.py
  │     │     └── core/causal_engine/causal_engine.py
  │     ├── core/agent/master_agent.py
  │     │     ├── core/agent/agent_manager.py
  │     │     │     ├── core/agent/worker_agent.py
  │     │     │     └── core/agent/worker_pool.py
  │     │     ├── core/agent/sub_agent.py
  │     │     └── core/agent/sub_agent_pool.py
  │     ├── core/llm/llm_client.py
  │     │     ├── core/llm/llm_switch.py
  │     │     ├── core/llm/data_filter.py
  │     │     └── core/llm/context_builder.py
  │     └── core/observation/observation_hub.py
  │           └── core/observation/event_bus.py
  ├── core/agent_main.py
  │     └── core/control/kernel_boot/ (内核启动)
  ├── core/control/controller.py
  ├── core/planning/planner.py / planner_v2.py
  ├── core/runtime/unified_coordinator.py
  │     └── core/runtime/execution_engine.py
  │           └── core/runtime/action_router.py
  └── core/bootstrap/wiring.py
        └── core/runtime/global_registry.py
```

### 4.2 关键依赖链 / Key Dependency Chains

| 依赖链 / Chain | 方向 / Direction |
|---|---|
| GlobalRegistry <- Wiring <- Controller | 注册表提供依赖注入 / Registry provides DI |
| EventBus <- MasterAgent <- ObservationHub | 事件驱动数据流 / Event-driven data flow |
| MemoryRouter <- MemoryKernel <- AgentComponents | 记忆路由驱动存储 / Memory router drives storage |
| LLMSwitch -> DataFilter -> LLMClient | 模式控制数据过滤 / Mode controls data filtering |
| RiskEvaluator -> SafetyOS -> DataChainCapsule | 风险评估驱动安全决策 / Risk eval drives safety decision |
| TimelineManager -> CausalEngine -> CausalJudge | 时间线驱动因果推理 / Timeline drives causal reasoning |

---

## 5. 测试脚本 / Test Scripts

| 脚本 / Script | 功能 / Function |
|---|---|
| `scripts/test_data_chain.py` | 基础数据链完整测试：SafetyOS审批 -> 时间线记录 -> 因果推理 / Basic data chain test |
| `scripts/test_data_chain_integration.py` | 数据链集成测试 / Data chain integration test |
| `scripts/test_golden_chain.py` | 黄金数据链测试：6阶段全链路闭环 / Golden data chain test with 6-stage full loop |
| `scripts/test_golden_chain_integration.py` | 黄金数据链集成测试 / Golden data chain integration test |
| `scripts/test_cognitive_flow.py` | 统一认知流系统测试：HypothesisEngine + AttentionUnified + CognitiveKernelV2 / Cognitive flow test |
| `scripts/test_full_pipeline.py` | 完整管道测试 / Full pipeline test |
| `scripts/test_full_round.py` | 完整轮次测试 / Full round test |
| `scripts/test_pipeline.py` | 管道测试 / Pipeline test |

---

## 6. 配置文件 / Configuration Files

| 文件 / File | 功能 / Function |
|---|---|
| `config/agent_config.yaml` | Agent核心配置（模型、参数、行为阈值）/ Agent core config |
| `config/agent_params.yaml` | Agent参数配置 / Agent parameter config |
| `config/module_registry.yaml` | 模块注册表配置 / Module registry config |
| `config/module_registry.py` | 模块注册表Python接口 / Module registry Python interface |
| `config/run_mode.py` | 运行模式配置 / Run mode config |
| `config/execution_gate.py` | 执行门控配置 / Execution gate config |
| `requirements.txt` | Python依赖包列表 / Python dependency list |
| `.gitignore` | Git忽略规则 / Git ignore rules |

---

## 数据流转测试结果 / Data Flow Test Results

```
模块导入测试 / Module Import Test: 38/38 PASSED
数据流实例化测试 / Data Flow Instantiation Test: 10/10 PASSED

详细 / Details:
1. Registry + EventBus: OK
2. MemoryKernel + Router: OK
3. LLM pipeline (Switch + Filter + Builder): OK
4. Task model: OK
5. Data chain v1: OK
6. SafetyOS approve: OK (decision=ask_human, risk=0.100)
7. Golden data chain: OK (via SafetyOS)
8. Cognitive runtime (Identity + Constitution + Motivation + Value): OK
9. PlannerV2 + GeneSandbox: OK
10. ValueVector: OK
```

---

*文档生成时间 / Document generated: 2026-06-15*
*Agent5 Core - Data Pipeline Connected Modules*
