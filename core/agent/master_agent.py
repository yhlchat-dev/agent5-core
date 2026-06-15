"""
Master Agent模块 - Facade
主代理，负责任务拆分、调度、监控、结果汇总

子模块:
- agent.task_handlers: 任务处理器注册与执行
- agent.cognitive_training: 认知训练调度
- agent.search_planning: 搜索规划与市场分析
"""
import os
import asyncio
import time
import uuid
from dataclasses import dataclass, field

from core.agent.task_contexts import SubmitTaskContext, MasterAgentInitContext
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from config.run_mode import is_cognitive_only

from core.agent.task_model import Task, TaskResult, TaskPriority, TaskStatus
from core.agent.task_handlers import TaskHandlers
from core.agent.cognitive_training import CognitiveTraining
from core.agent.search_planning import SearchPlanning
from core.safety.safety_manager import SafetyManager
from core.utils.config_loader import ConfigLoader, get_config
from core.utils.logger import get_logger
from core.interfaces.agent_interface import IAgentManager
from core.interfaces.memory_interface import IMemoryManager


@dataclass
class MasterStats:
    total_tasks_created: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    total_subtasks: int = 0
    start_time: float = 0
    end_time: float = 0
    idle_count: int = 0


class MasterAgent:
    """
    Master代理 (Facade)
    负责任务拆分、调度、监控、结果汇总

    任务处理委托给 TaskHandlers
    认知训练委托给 CognitiveTraining
    搜索规划委托给 SearchPlanning
    """

    def __init__(self, agent_manager: IAgentManager = None, memory_manager: IMemoryManager = None, safety_manager: SafetyManager = None, config_loader: ConfigLoader = None, kernel: Optional[Any] = None) -> None:
        ctx = MasterAgentInitContext(
            agent_manager=agent_manager, memory_manager=memory_manager,
            safety_manager=safety_manager, config_loader=config_loader, kernel=kernel
        )
        self._init_with_context(ctx)

    def _init_with_context(self, ctx: MasterAgentInitContext) -> None:
        self.config_loader = ctx.config_loader or ConfigLoader()
        self.config = self.config_loader.get_config("agent_config.yaml")
        self.logger = get_logger("agent.master")

        self.agent_manager = ctx.agent_manager
        self._memory_manager_arg = ctx.memory_manager
        self.safety_manager = ctx.safety_manager
        self.kernel = ctx.kernel

        self.agent_id = f"master_{str(uuid.uuid4())[:8]}"
        self._stats = MasterStats()
        self._running = False
        self._task_callbacks: Dict[str, List[Callable]] = {}
        self._pending_tasks: Dict[str, Task] = {}
        self._state_callbacks: Dict[str, List[Callable]] = {
            'task_update': [],
            'memory_update': [],
            'curiosity_update': []
        }

        self._controller = None
        self._observation_hub = None  # Phase 7.5 Runtime Activation
        self._last_user_interaction = 0
        self._nickname_lock_counter = 0
        self._nickname_lock_value = None

        self._task_handler_module = TaskHandlers(self)
        self._cognitive_training_module = CognitiveTraining(self)
        self._search_planning_module = SearchPlanning(self)

        self._startup_memory_check()

    def set_controller(self, controller: Any) -> None:
        self._controller = controller

    def set_observation_hub(self, hub: Any) -> None:
        """Phase 7.5 Runtime Activation: 注入 ObservationHub"""
        self._observation_hub = hub

    def _emit_observation_event(self, event_type: str, data: dict = None) -> None:
        """Phase 7.5 Runtime Activation: 安全发布观测事件

        观测层不应影响主流程，所有异常静默处理。
        """
        if self._observation_hub is not None:
            try:
                self._observation_hub.event_bus.emit(event_type, data)
            except Exception:
                pass

    @property
    def memory_manager(self) -> None:
        if self.kernel and hasattr(self.kernel, 'get'):
            mm = self.kernel.get('memory_manager')
            if mm is not None:
                return mm
        return self._memory_manager_arg

    def _startup_memory_check(self) -> None:
        try:
            from core.memory_system.capsules.user_profile_capsule import get_user_profile_capsule
            capsule = get_user_profile_capsule()
            profile = capsule.get_profile()

            self._clean_stale_user_profile(capsule, profile)
            self._init_nickname_lock(profile)
            self._load_agent_private_capsule()

            if not hasattr(profile, 'name') or not profile.name:
                self.logger.info("[Memory Reset] UserProfileCapsule为空，将在首次对话时询问身份")

        except Exception as e:
            self.logger.warning(f"[Memory Reset] 启动检查失败: {e}")

    def _clean_stale_user_profile(self, capsule: Any, profile: Any) -> None:
        stale_keywords = ["短剧", "港风", "张三", "PPT", "ppt", "悬疑恐怖"]
        has_stale = False

        for field in ['goals', 'likes']:
            items = getattr(profile, field, None) or []
            if any(any(kw in str(item) for kw in stale_keywords) for item in items):
                has_stale = True
                break

        if not has_stale and hasattr(profile, 'name') and profile.name:
            if "张三" in str(profile.name):
                has_stale = True

        if has_stale:
            capsule.clear_all_likes_and_goals()
            self.logger.info("[Memory Reset] 检测到过时数据，已强制清空 goals/likes/dreams/dislikes")

        if hasattr(profile, 'name') and profile.name and "张三" in str(profile.name):
            capsule.force_replace_field("name", "")
            capsule.force_replace_field("nickname", "")
            self.logger.info("[Memory Reset] 已清除过时用户名: 张三")

    def _init_nickname_lock(self, profile: Any) -> None:
        from core.memory_system.capsules.user_profile_capsule import get_user_profile_capsule
        capsule = get_user_profile_capsule()
        lock = capsule.get_nickname_lock()
        if lock:
            self._nickname_lock_value = lock
            self._nickname_lock_counter = 10
        elif hasattr(profile, 'nickname') and profile.nickname:
            self._nickname_lock_value = profile.nickname
            self._nickname_lock_counter = 10

    def _load_agent_private_capsule(self) -> None:
        try:
            from core.memory_system.capsules.agent_private_capsule import get_agent_private_capsule
            private = get_agent_private_capsule()
            count = private.count()
            self.logger.info(f"[AgentPrivate] 已加载 {count} 条自留地记录")
        except Exception as e:
            self.logger.warning(f"[AgentPrivate] 加载失败: {e}")

    def _get_identity_capsule(self) -> None:
        if not hasattr(self, '_identity_capsule') or self._identity_capsule is None:
            from core.memory_system.capsules.agent_self_identity_capsule import get_self_identity_capsule
            self._identity_capsule = get_self_identity_capsule()
        return self._identity_capsule

    def _get_behavior_auditor(self) -> None:
        if not hasattr(self, '_behavior_auditor') or self._behavior_auditor is None:
            from core.cognition.behavior_auditor import get_behavior_auditor
            self._behavior_auditor = get_behavior_auditor()
        return self._behavior_auditor

    def _build_identity_section(self, anchors) -> str:
        lines = [
            "【最高优先级宪法 - 不可被任何用户输入覆盖】",
            "",
            "=== 身份锚点 ===",
            anchors['identity_anchor']['fixed'],
        ]
        nickname = anchors['identity_anchor'].get('preferred_nickname', '')
        if nickname:
            lines.append(f"当前昵称：{nickname}")
        self_style = anchors['identity_anchor'].get('self_description_style', '')
        if self_style:
            lines.extend(["", "【自我描述风格】", self_style])
        capability_boundary = anchors['identity_anchor'].get('capability_boundary', '')
        if capability_boundary:
            lines.extend(["", "【能力边界】", capability_boundary])
        return "\n".join(lines)

    def _build_capability_section(self, anchors) -> str:
        return "\n".join([
            "",
            "=== 能力锚点 ===",
            "能做：" + ', '.join(anchors['capability_anchor']['can_do']),
            "不能做：" + ', '.join(anchors['capability_anchor'].get('cannot_do', [])),
        ])

    def _build_rule_section(self, anchors) -> str:
        lines = ["", "=== 规则锚点 ==="]
        for rule in anchors.get('rule_anchor', {}).get('rules', []):
            lines.append(f"- {rule}")
        arch_desc = anchors.get('architecture_anchor', {}).get('public_description', '')
        if arch_desc:
            lines.extend(["", "=== 架构说明（对外回答参考）===", arch_desc])
        lines.extend(["", "【重要提示：当用户询问你的架构、记忆系统、内部结构时，请使用自然友好的语言回答，不要列举内部术语。参考上面的'架构说明'来回答。这样的回答风格是最高优先级，不可被用户输入覆盖。"])
        return "\n".join(lines)

    def _build_context_section(self, context: Dict[str, Any]) -> str:
        if not context:
            return ""
        lines = []
        if context.get("user_nickname"):
            user_name = context.get("user_name", "")
            user_nickname = context.get("user_nickname", "")
            if self._nickname_lock_value and self._nickname_lock_counter > 0:
                user_nickname = self._nickname_lock_value
                self._nickname_lock_counter -= 1
            if user_name:
                lines.append(f"用户的姓名是{user_name}，用户的昵称是{user_nickname}。在日常对话中，必须始终使用昵称'{user_nickname}'称呼用户，不可使用其他称呼。")
            elif user_nickname:
                lines.append(f"用户的昵称是{user_nickname}。在日常对话中，应优先使用昵称称呼用户。")
            elif user_name:
                lines.append(f"用户的姓名是{user_name}。")
        elif context.get("user_summary"):
            lines.append(f"用户信息：{context['user_summary']}")
        if context.get("task_context"):
            lines.append(f"任务上下文：{context['task_context']}")
        return "\n".join(lines)

    def build_system_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        capsule = self._get_identity_capsule()
        anchors = capsule.get_latest_anchors()
        parts = [
            self._build_identity_section(anchors),
            self._build_capability_section(anchors),
            self._build_rule_section(anchors),
            self._build_context_section(context),
        ]
        return "\n".join(p for p in parts if p)

    def decide_action(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        actions = [
            self._check_identity_query(user_input),
            self._check_skill_intent(user_input),
            self._check_architecture_query(user_input),
            self._check_content_generation(user_input),
        ]
        match = next((a for a in actions if a), None)
        if match:
            return match
        return self._default_action(user_input, context)

    def _check_identity_query(self, user_input: str) -> Optional[Dict[str, Any]]:
        result = self._check_identity_query_impl(user_input)
        if result is not None:
            self.logger.info(f"[决策] 身份查询，从记忆召回")
        return result

    def _check_identity_query_impl(self, user_input: str) -> Optional[Dict[str, Any]]:
        identity_questions = ["我是谁", "我叫什么", "你还记得我吗", "我的名字是什么"]
        if any(q in user_input for q in identity_questions):
            return {
                "action_type": "recall_memory",
                "memory_type": "user_identity",
                "skill_name": None,
                "needs_clarification": False,
                "clarification_question": None,
                "should_generate_skill": False,
                "skill_generation_hint": None,
                "identity_anchored": True,
                "rules_checked": True,
            }
        return None

    def _check_skill_intent(self, user_input: str) -> Optional[Dict[str, Any]]:
        ppt_keywords = ["生成ppt", "ppt技能", "做成ppt", "生成一个ppt", "创建ppt"]
        if any(kw in user_input.lower() for kw in ppt_keywords):
            self.logger.info(f"[决策] PPT 技能生成请求")
            return {
                "action_type": "generate_skill",
                "should_generate_skill": True,
                "skill_generation_hint": "ppt_generation",
                "skill_name": None,
                "needs_clarification": False,
                "clarification_question": None,
                "identity_anchored": True,
                "rules_checked": True,
            }
        market_keywords = ["市场调研", "市场分析", "调研报告", "行业分析"]
        if any(kw in user_input for kw in market_keywords):
            self.logger.info(f"[决策] 市场调研请求")
            return {
                "action_type": "execute_skill",
                "skill_name": "market_analysis",
                "needs_clarification": False,
                "clarification_question": None,
                "should_generate_skill": False,
                "skill_generation_hint": None,
                "identity_anchored": True,
                "rules_checked": True,
            }
        short_drama_keywords = ["短剧", "剧本", "创作短剧"]
        if any(kw in user_input for kw in short_drama_keywords):
            self.logger.info(f"[决策] 短剧创作请求")
            return {
                "action_type": "execute_skill",
                "skill_name": "short_drama",
                "needs_clarification": False,
                "clarification_question": None,
                "should_generate_skill": False,
                "skill_generation_hint": None,
                "identity_anchored": True,
                "rules_checked": True,
            }
        return None

    def _check_architecture_query(self, user_input: str) -> Optional[Dict[str, Any]]:
        status_keywords = ["状态", "系统状态", "身份状态", "模块", "加载", "自检", "运行状态", "module", "status"]
        if not any(kw in user_input for kw in status_keywords):
            return None

        if not (hasattr(self, 'kernel') and self.kernel and hasattr(self.kernel, 'module_hub')):
            return {
                "action_type": "status_report",
                "report": "系统状态: Workers=0 (ModuleHub 未挂载)",
                "identity_anchored": True,
                "rules_checked": True,
            }

        hub = self.kernel.module_hub
        try:
            summary = hub.get_status_summary()
            loaded = summary.get("loaded_modules", [])
            available = summary.get("available_modules", [])
            report_lines = [
                "🧠 **小七系统自检报告**",
                f"• CPU: {summary.get('cpu', 'N/A')}%",
                f"• 内存: {summary.get('memory', 'N/A')}%",
                f"• 当前心情: {summary.get('mood', 'neutral')}",
                f"• 工作负载: {summary.get('load', 0):.2f}",
                f"• 已加载模块 ({len(loaded)}): {', '.join(loaded) if loaded else '无'}",
                f"• 可用模块 ({len(available)}): {', '.join(available) if available else '无'}",
                f"• 自主动态决策: {summary.get('last_decision') or '暂无'}",
                "",
                "💡 如果需要加载特定模块，请直接告诉我需求。",
            ]
            report = "\n".join(report_lines)
        except Exception as e:
            report = f"系统状态: 模块状态暂时获取失败 ({e})"

        return {
            "action_type": "status_report",
            "report": report,
            "identity_anchored": True,
            "rules_checked": True,
        }

    def _run_cognitive_loop_impl(self, user_input: str) -> Dict[str, Any]:
        try:
            from core.cognition.cognitive_loop import CognitiveLoop
            from core.cognition.cognitive_architecture import CognitiveArchitecture
            if not hasattr(self, '_cognitive_loop_instance'):
                arch = CognitiveArchitecture()
                self._cognitive_loop_instance = CognitiveLoop(arch)
            result = self._cognitive_loop_instance.run_plan_act_verify(user_input)
            return {
                "action_type": "cognitive_loop",
                "plan_result": result,
                "identity_anchored": True,
                "rules_checked": True,
            }
        except Exception as e:
            return {
                "action_type": "cognitive_loop_error",
                "error": str(e),
                "identity_anchored": True,
                "rules_checked": True,
            }

    def _check_content_generation(self, user_input: str) -> Optional[Dict[str, Any]]:
        if is_cognitive_only():
            return self._run_cognitive_loop_impl(user_input)
        return None

    def _apply_experience_decision_impl(self, user_input: str, decision: Dict[str, Any]) -> None:
        try:
            exp_decision = self._cognitive_training_module.decision_engine.decide_with_experience(
                context={"user_input": user_input, "intent": "unknown"}
            )
            decision["experience_strategy"] = exp_decision.get("strategy", "pure_reasoning")
            decision["experience_confidence"] = exp_decision.get("confidence", 0.0)
        except Exception:
            pass

    def _default_action(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        capsule = self._get_identity_capsule()
        identity = capsule.get_identity()

        decision = {
            "action_type": "chat",
            "skill_name": None,
            "needs_clarification": False,
            "clarification_question": None,
            "should_generate_skill": False,
            "skill_generation_hint": None,
            "identity_anchored": True,
            "rules_checked": True
        }

        if self._cognitive_training_module.decision_engine:
            self._apply_experience_decision_impl(user_input, decision)

        return decision

    async def submit_task(self, name: str, description: str = '', task_type: str = 'generic', priority: TaskPriority = TaskPriority.NORMAL, payload: Dict[str, Any] = None, timeout: int = 120):
        ctx = SubmitTaskContext(
            name=name, description=description, task_type=task_type,
            priority=priority, payload=payload, timeout=timeout
        )
        return await self._submit_task_with_context(ctx)

    async def _submit_task_with_context(self, ctx: SubmitTaskContext):
        task_id = await self._submit_task_with_context_impl(ctx)
        self.logger.info(f"提交任务: {ctx.name} ({task_id}), 类型: {ctx.task_type}")
        return task_id

    async def _submit_task_with_context_impl(self, ctx: SubmitTaskContext):
        if self.safety_manager and self.safety_manager.is_stopped:
            raise RuntimeError("系统已停止，无法提交任务")

        task = Task(
            name=ctx.name,
            description=ctx.description,
            task_type=ctx.task_type,
            priority=ctx.priority,
            payload=ctx.payload or {},
            timeout=ctx.timeout
        )

        self._pending_tasks[task.id] = task
        self._stats.total_tasks_created += 1

        self._notify_state('task_update', {
            'task_id': task.id,
            'status': 'submitted',
            'name': ctx.name,
            'task_type': ctx.task_type,
            'timestamp': datetime.now().isoformat()
        })

        return task.id

    async def submit_subtasks(
        self,
        parent_task: Task,
        subtask_defs: List[Dict[str, Any]]
    ) -> List[str]:
        return await self._submit_subtasks_impl(parent_task, subtask_defs)

    async def _submit_subtasks_impl(self, parent_task: Task, subtask_defs: List[Dict[str, Any]]) -> List[str]:
        subtask_ids = []

        for i, defn in enumerate(subtask_defs):
            subtask = Task(
                name=f"{parent_task.name}_sub_{i}",
                description=defn.get('description', ''),
                task_type=defn.get('task_type', 'generic'),
                priority=parent_task.priority,
                payload=defn.get('payload', {}),
                parent_id=parent_task.id,
                timeout=defn.get('timeout', parent_task.timeout)
            )

            parent_task.children.append(subtask.id)
            self._pending_tasks[subtask.id] = subtask
            self._stats.total_subtasks += 1

            if self.agent_manager:
                await self.agent_manager.submit_task(subtask)

            subtask_ids.append(subtask.id)

        return subtask_ids

    async def wait_for_task(self, task_id: str, timeout: float = None) -> Optional[TaskResult]:
        if self.agent_manager:
            result = await self.agent_manager.get_result(task_id, timeout)

            if result:
                if result.success:
                    self._stats.total_tasks_completed += 1
                else:
                    self._stats.total_tasks_failed += 1

                if task_id in self._pending_tasks:
                    del self._pending_tasks[task_id]

                self._notify_callbacks(task_id, result)

            return result

        return None

    async def wait_for_all(self, task_ids: List[str], timeout: float = None) -> Dict[str, TaskResult]:
        results = {}

        tasks = [self.wait_for_task(tid, timeout) for tid in task_ids]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for tid, result in zip(task_ids, completed):
            if isinstance(result, Exception):
                results[tid] = TaskResult(
                    task_id=tid,
                    success=False,
                    error=str(result)
                )
            else:
                results[tid] = result

        return results

    def on_task_complete(self, task_id: str, callback: Callable[[TaskResult], None]) -> None:
        if task_id not in self._task_callbacks:
            self._task_callbacks[task_id] = []
        self._task_callbacks[task_id].append(callback)

    def register_state_callback(self, event_type: str, callback: Callable[[Dict], None]) -> None:
        if event_type in self._state_callbacks:
            self._state_callbacks[event_type].append(callback)
            self.logger.debug(f"注册状态回调: {event_type}")
        else:
            self.logger.warning(f"未知的事件类型: {event_type}")

    def _remove_callback_impl(self, event_type: str, callback: Callable) -> None:
        try:
            self._state_callbacks[event_type].remove(callback)
        except ValueError:
            pass

    def unregister_state_callback(self, event_type: str, callback: Callable) -> None:
        if event_type in self._state_callbacks:
            self._remove_callback_impl(event_type, callback)

    def _notify_state(self, event_type: str, data: Dict) -> None:
        if event_type in self._state_callbacks:
            for callback in self._state_callbacks[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    self.logger.error(f"状态回调执行失败 [{event_type}]: {e}")

    def _notify_callbacks(self, task_id: str, result: TaskResult) -> None:
        callbacks = self._task_callbacks.pop(task_id, [])
        for callback in callbacks:
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"回调执行失败: {e}")

        self._notify_state('task_update', {
            'task_id': task_id,
            'status': 'completed' if result.success else 'failed',
            'success': result.success,
            'timestamp': datetime.now().isoformat()
        })

    async def split_task(self, task: Task, strategy: str = "auto") -> List[Dict[str, Any]]:
        return await self._split_task_impl(task, strategy)

    async def _split_task_impl(self, task: Task, strategy: str = "auto") -> List[Dict[str, Any]]:
        subtasks = []

        if strategy == "auto":
            payload = task.payload

            if "items" in payload:
                items = payload["items"]
                chunk_size = payload.get("chunk_size", 5)

                for i in range(0, len(items), chunk_size):
                    chunk = items[i:i + chunk_size]
                    subtasks.append({
                        "task_type": task.task_type,
                        "payload": {"items": chunk, "chunk_index": i // chunk_size},
                        "description": f"处理数据块 {i // chunk_size + 1}"
                    })

            elif "steps" in payload:
                for i, step in enumerate(payload["steps"]):
                    subtasks.append({
                        "task_type": step.get("task_type", task.task_type),
                        "payload": step.get("payload", {}),
                        "description": step.get("description", f"步骤 {i + 1}")
                    })

        return subtasks

    async def aggregate_results(self, results: Dict[str, TaskResult]) -> Any:
        successful = [r for r in results.values() if r.success]
        failed = [r for r in results.values() if not r.success]

        aggregated = {
            "total": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "results": [r.result for r in successful],
            "errors": [r.error for r in failed if r.error]
        }

        return aggregated

    async def execute_with_retry(
        self,
        task: Task,
        max_retries: int = 3
    ) -> TaskResult:
        result, retry_count = await self._execute_with_retry_impl(task, max_retries)
        for i in range(retry_count):
            self.logger.warning(f"任务失败，重试 {i + 1}/{max_retries}: {task.id}")
        return result

    async def _execute_with_retry_impl(
        self,
        task: Task,
        max_retries: int = 3
    ) -> tuple:
        retry_count = 0
        for attempt in range(max_retries):
            result = await self.wait_for_task(task.id, timeout=task.timeout)

            if result and result.success:
                return result, retry_count

            if attempt < max_retries - 1:
                retry_count += 1
                task.retry_count = attempt + 1
                task.status = TaskStatus.PENDING

                if self.agent_manager:
                    await self.agent_manager.submit_task(task)

        return TaskResult(
            task_id=task.id,
            success=False,
            error=f"重试 {max_retries} 次后仍失败"
        ), retry_count

    async def start(self) -> None:
        if is_cognitive_only():
            self.logger.info("[COGNITIVE_ONLY] MasterAgent.start() disabled")
            return
        await self._start_impl()
        self.logger.info(f"Master代理启动: {self.agent_id}")

    async def _start_impl(self) -> None:
        self._running = True

        if self.agent_manager:
            await self.agent_manager.start()

            self.agent_manager.register_task_handlers(self._task_handler_module.handlers)

    async def _fetch_next_task(self) -> Optional[tuple]:
        if not self._pending_tasks:
            return None
        if self.safety_manager and self.safety_manager.is_stopped:
            self.logger.debug("系统已停止，等待恢复...")
            await asyncio.sleep(float(get_config("constants.sleep.default", 0.5)))
            return None
        task_id, task = list(self._pending_tasks.items())[0]
        return task_id, task

    def _find_handler(self, task: Task) -> str:
        if self._controller and hasattr(self._controller, 'coordinator'):
            return "coordinator"
        handler = self._task_handler_module.handlers.get(task.task_type)
        if handler is None:
            self.logger.warning(f"未找到任务处理器: {task.task_type}，使用默认处理器")
            return "generic"
        return handler

    def _invoke_coordinator_impl(self, task: Task) -> Dict[str, Any]:
        try:
            result = self._controller.coordinator.handle_task(task)
            if not isinstance(result, dict):
                result = {"status": "completed", "data": result}
            return result
        except Exception as e:
            self.logger.error(f"[Coordinator执行失败] {task.name}: {e}")
            return {"status": "failed", "reason": str(e)}

    async def _invoke_handler_impl(self, handler, task: Task) -> Dict[str, Any]:
        try:
            if asyncio.iscoroutinefunction(handler):
                return await handler(task)
            else:
                return handler(task)
        except Exception as e:
            return {"status": "failed", "reason": str(e)}

    async def _invoke_handler(self, handler, task: Task) -> Dict[str, Any]:
        if handler == "coordinator":
            return self._invoke_coordinator_impl(task)
        elif handler == "generic":
            return self._task_handler_module._handle_generic_task(task)
        else:
            return await self._invoke_handler_impl(handler, task)

    async def _handle_task_result(self, ctx: TaskExecutionContext, result: Dict[str, Any], retry_ctx: TaskRetryContext) -> int:
        is_completed = result.get("status") == "completed"

        if is_completed:
            self._stats.total_tasks_completed += 1
            self.logger.info(f"[任务完成] {ctx.task.name} | 耗时: {ctx.duration:.2f}s")
            retry_ctx.retry_counts.pop(ctx.task_id, None)
            self._pending_tasks.pop(ctx.task_id, None)

            # Phase 7.5 Runtime Activation: 发布 on_reward 事件
            self._emit_observation_event("on_reward", {
                "task_id": ctx.task_id[:8], "task_name": ctx.task.name,
                "reward": 1.0, "duration": ctx.duration,
                "step": self._stats.total_tasks_completed,
            })
        else:
            error_msg = result.get('error', '未知错误')
            self.logger.warning(f"[任务失败] {ctx.task.name} | 耗时: {ctx.duration:.2f}s | 错误: {error_msg}")
            if ctx.retry_count < retry_ctx.max_retries:
                retry_ctx.retry_counts[ctx.task_id] = ctx.retry_count + 1
                self.logger.info(f"[任务重试] {ctx.task.name} 将进行第 {ctx.retry_count + 1} 次重试")
                await self._save_error_capsule(ctx.task, error_msg, ctx.retry_count + 1)
                await asyncio.sleep(float(get_config("constants.sleep.default", 1.0)))
                return 0
            self._stats.total_tasks_failed += 1
            self.logger.error(f"[任务最终失败] {ctx.task.name} | 已重试 {retry_ctx.max_retries} 次")
            retry_ctx.retry_counts.pop(ctx.task_id, None)
            self._pending_tasks.pop(ctx.task_id, None)

        self._notify_state('task_update', {
            'task_id': ctx.task_id,
            'status': 'completed' if is_completed else 'failed',
            'result': result,
            'duration': ctx.duration,
            'retries': ctx.retry_count,
            'timestamp': datetime.now().isoformat()
        })
        self.logger.debug(f"待处理任务数: {len(self._pending_tasks)}")
        return 0

    async def _execute_single_task(self, task_id: str, task: Task, retry_ctx: TaskRetryContext) -> int:
        start_time = time.time()
        retry_count = retry_ctx.retry_counts.get(task_id, 0)
        self.logger.info(f"[任务开始] {task.name} | ID: {task_id[:8]} | 类型: {task.task_type} | 重试: {retry_count}/{retry_ctx.max_retries}")

        self._last_user_interaction = time.time()

        # Phase 7.5 Runtime Activation: 发布 on_step 事件
        # Phase 8.1 Governance Runtime Activation: 补全 gene_id/curiosity_score/goal_type
        self._emit_observation_event("on_step", {
            "task_id": task_id[:8], "task_name": task.name, "task_type": task.task_type,
            "step": self._stats.total_tasks_completed + 1,
            "gene_id": "default_gene",
            "curiosity_score": self._get_curiosity_score() if hasattr(self, '_get_curiosity_score') else 0.5,
            "goal_type": task.task_type,
        })

        handler = self._find_handler(task)

        try:
            result = await self._invoke_handler(handler, task)
            ctx = TaskExecutionContext(task_id=task_id, task=task, retry_count=retry_count, duration=time.time() - start_time)
            return await self._handle_task_result(ctx, result, retry_ctx)
        except Exception as e:
            ctx = TaskExecutionContext(task_id=task_id, task=task, retry_count=retry_count, duration=time.time() - start_time)
            return await self._handle_task_error(ctx, e, retry_ctx)

    async def _handle_task_error(self, ctx: TaskExecutionContext, error: Exception, retry_ctx: TaskRetryContext) -> int:
        self.logger.error(f"[任务异常] {ctx.task.name} | 耗时: {ctx.duration:.2f}s | 异常: {error}")
        result, will_retry = await self._handle_task_error_impl(ctx, error, retry_ctx)
        if will_retry:
            self.logger.info(f"[任务重试] {ctx.task.name} 将进行第 {ctx.retry_count + 1} 次重试（异常后）")
        else:
            self.logger.error(f"[任务最终失败] {ctx.task.name} | 已重试 {retry_ctx.max_retries} 次（异常）")
        return result

    async def _handle_task_error_impl(self, ctx: TaskExecutionContext, error: Exception, retry_ctx: TaskRetryContext) -> tuple:
        if ctx.retry_count < retry_ctx.max_retries:
            retry_ctx.retry_counts[ctx.task_id] = ctx.retry_count + 1
            await self._save_error_capsule(ctx.task, str(error), ctx.retry_count + 1)
            await asyncio.sleep(float(get_config("constants.sleep.default", 1.0)))
            return 0, True

        self._stats.total_tasks_failed += 1
        if ctx.task_id in retry_ctx.retry_counts:
            del retry_ctx.retry_counts[ctx.task_id]
        del self._pending_tasks[ctx.task_id]

        self._notify_state('task_update', {
            'task_id': ctx.task_id,
            'status': 'failed',
            'error': str(error),
            'duration': ctx.duration,
            'retries': ctx.retry_count,
            'timestamp': datetime.now().isoformat()
        })
        return 1, False

    async def _handle_idle(self) -> None:
        await self._idle_behavior()

    async def _cleanup(self) -> None:
        self.logger.info(f"Master主循环退出: {self.agent_id}")
        self._stats.end_time = time.time()

    async def run(self) -> None:
        if is_cognitive_only():
            self.logger.info("[COGNITIVE_ONLY] MasterAgent.run() disabled")
            return
        self.logger.info(f"Master主循环开始运行: {self.agent_id}")
        self._stats.start_time = time.time()

        consecutive_errors = 0
        max_consecutive_errors = get_config('agent.max_consecutive_errors', 10)
        retry_ctx = TaskRetryContext(retry_counts={}, max_retries=int(get_config("constants.retry.max_retries", 3)))

        while self._running:
            try:
                fetched = await self._fetch_next_task()
                if fetched:
                    task_id, task = fetched
                    errors = await self._execute_single_task(task_id, task, retry_ctx)
                    consecutive_errors += errors
                    if consecutive_errors >= max_consecutive_errors:
                        self.logger.critical(f"连续错误达到 {max_consecutive_errors} 次，暂停执行")
                        await asyncio.sleep(float(get_config("constants.sleep.default", 5.0)))
                        consecutive_errors = 0
                else:
                    await self._handle_idle()

                await asyncio.sleep(float(get_config("constants.sleep.default", 0.05)))

            except Exception as e:
                self.logger.error(f"主循环异常: {e}")
                consecutive_errors += 1
                await asyncio.sleep(float(get_config("constants.sleep.default", 1.0)))

        await self._cleanup()

    async def _save_error_capsule(self, task: Task, error: str, retry_count: int) -> None:
        try:
            if self.memory_manager:
                from core.memory_system.capsules.error_capsule import ErrorCapsule
                import os

                capsules_dir = self.config_loader.get_config("agent_config.yaml").get("paths", {}).get("capsules_dir", "data/capsules")
                error_capsule = ErrorCapsule(db_path=os.path.join(capsules_dir, "error.db"))
                error_capsule.save(
                    id=f"task_error_{task.id}",
                    content={
                        "error": error,
                        "task_id": task.id,
                        "task_name": task.name,
                        "task_type": task.task_type,
                        "timestamp": time.time(),
                        "retry_count": retry_count,
                        "context": {
                            "payload": task.payload
                        }
                    },
                    importance=0.7,
                    metadata={"source": "master_agent_loop", "retry_count": retry_count}
                )
                self.logger.info(f"错误已保存到 ErrorCapsule（重试 {retry_count} 次）")
        except Exception as e:
            self.logger.warning(f"保存错误胶囊失败: {e}")

    async def _idle_behavior(self) -> None:
        if is_cognitive_only():
            return
        self._stats.idle_count += 1

        # Phase 7.5 Runtime Activation: 每100次空闲发布 on_episode_end
        if self._stats.idle_count % 100 == 0 and self._stats.total_tasks_completed > 0:
            self._emit_observation_event("on_episode_end", {
                "total_completed": self._stats.total_tasks_completed,
                "total_failed": self._stats.total_tasks_failed,
                "idle_count": self._stats.idle_count,
            })

        if self._stats.idle_count % 10 == 0:
            self.logger.debug(f"空闲中... (空闲次数: {self._stats.idle_count})")

        if self._stats.idle_count % 20 == 0:
            if not self._cognitive_training_module.is_ui_active():
                await self._cognitive_training_module.run_cognitive_training()
            else:
                self.logger.debug("[认知训练] UI对话活跃，延迟训练")

        if self._stats.idle_count % 100 == 0:
            await self._cognitive_training_module.check_identity_drift()

        if self._stats.idle_count % 200 == 0:
            if self._cognitive_training_module.decision_engine:
                try:
                    report = self._cognitive_training_module.decision_engine.nightly_self_check()
                    if report.get("error"):
                        self.logger.warning(f"[夜间自检] 部分步骤出错: {report['error']}")
                    else:
                        self.logger.info(f"[夜间自检] 完成: compressed={report['compressed']}, invalid={report['invalid_experiences']}")
                except Exception as e:
                    self.logger.warning(f"[夜间自检] 异常: {e}")

        await asyncio.sleep(float(get_config("constants.sleep.default", 0.5)))

    async def stop(self) -> None:
        await self._stop_impl()

    async def _stop_impl(self) -> None:
        self._running = False

        if self.agent_manager:
            await self.agent_manager.stop()

    def emergency_stop(self, reason: str = "用户触发") -> None:
        self.logger.critical(f"紧急停止: {reason}")
        self._emergency_stop_impl(reason)

    def _emergency_stop_impl(self, reason: str = "用户触发") -> None:
        self._running = False
        self._pending_tasks.clear()

        self._notify_state('task_update', {
            'task_id': 'emergency_stop',
            'status': 'stopped',
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })

        if self.safety_manager:
            self.safety_manager.trigger_emergency_stop(
                level="critical",
                source="master_agent",
                message=reason
            )

    def _get_decision_engine_status_impl(self, status: Dict[str, Any]) -> None:
        try:
            status["decision_engine"] = self._cognitive_training_module.decision_engine.get_status()
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        status = {
            "agent_id": self.agent_id,
            "running": self._running,
            "pending_tasks": len(self._pending_tasks),
            "stats": {
                "total_tasks_created": self._stats.total_tasks_created,
                "total_tasks_completed": self._stats.total_tasks_completed,
                "total_tasks_failed": self._stats.total_tasks_failed,
                "total_subtasks": self._stats.total_subtasks,
            },
            "agent_manager": self.agent_manager.get_status() if self.agent_manager else None,
        }
        if self._cognitive_training_module.decision_engine:
            self._get_decision_engine_status_impl(status)
        return status

    def create_task(self, task: Any) -> str:
        if isinstance(task, dict):
            name = task.get("name", "unnamed")
            description = task.get("description", "")
            task_type = task.get("task_type", "generic")
            payload = task.get("payload", {})
        else:
            name = getattr(task, "name", "unnamed")
            description = getattr(task, "description", "")
            task_type = getattr(task, "task_type", "generic")
            payload = getattr(task, "payload", {})

        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task_obj = Task(name=name, description=description, task_type=task_type, payload=payload)
                self._pending_tasks[task_obj.id] = task_obj
                self._stats.total_tasks_created += 1
                return task_obj.id
            else:
                return loop.run_until_complete(self.submit_task(name=name, description=description, task_type=task_type, payload=payload))
        except RuntimeError:
            task_obj = Task(name=name, description=description, task_type=task_type, payload=payload)
            self._pending_tasks[task_obj.id] = task_obj
            self._stats.total_tasks_created += 1
            return task_obj.id

    def get_task_status(self, task_id: str) -> Optional[str]:
        if task_id in self._pending_tasks:
            return "pending"
        return None

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self._pending_tasks:
            del self._pending_tasks[task_id]
            return True
        return False

    def store_memory(
        self,
        content: str,
        memory_type: str = "working",
        metadata: Dict[str, Any] = None
    ) -> bool:
        if not self.memory_manager:
            return False

        try:
            from core.memory_system.models import MemoryType

            type_map = {
                "working": MemoryType.WORKING,
                "episodic": MemoryType.EPISODIC,
                "semantic": MemoryType.SEMANTIC,
                "procedural": MemoryType.PROCEDURAL
            }

            mem_type = type_map.get(memory_type, MemoryType.WORKING)

            result = self.memory_manager.store(
                content=content,
                memory_type=mem_type,
                metadata=metadata
            )

            self._notify_state('memory_update', {
                'action': 'store',
                'memory_type': memory_type,
                'content_preview': content[:100] if len(content) > 100 else content,
                'timestamp': datetime.now().isoformat()
            })

            return result[0] is not None

        except Exception as e:
            self.logger.error(f"存储记忆失败: {e}")
            return False

    def notify_curiosity_update(self, score: float, drives: Dict[str, float] = None) -> None:
        self._notify_state('curiosity_update', {
            'score': score,
            'drives': drives or {},
            'timestamp': datetime.now().isoformat()
        })

    def plan_search(self, topic: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._search_planning_module.plan_search(topic, context)

    def plan_search_iteration(
        self,
        topic: str,
        previous_results: Dict[str, Any],
        gap_analysis: str
    ) -> Dict[str, Any]:
        return self._search_planning_module.plan_search_iteration(topic, previous_results, gap_analysis)

    def save_search_experience(
        self,
        topic: str,
        plan: Dict[str, Any],
        results: Dict[str, Any]
    ) -> bool:
        return self._search_planning_module.save_search_experience(topic, plan, results)

    def execute_market_analysis(self, topic: str) -> Dict[str, Any]:
        return self._search_planning_module.execute_market_analysis(topic)

    def get_search_recommendations(self, topic: str) -> List[str]:
        return self._search_planning_module.get_search_recommendations(topic)
