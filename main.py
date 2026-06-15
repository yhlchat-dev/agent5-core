import sys
import os
import asyncio
import threading
import argparse
import signal
from pathlib import Path
from typing import Optional, Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from config.run_mode import is_cognitive_only, reload_run_mode
from config.module_registry import should_enable_module, allow_background_tasks

if is_cognitive_only():
    from core.guard.system_lock import block_async
    block_async()
    print("[COGNITIVE_ONLY] System lock engaged")

from core.utils.config_loader import ConfigLoader
from core.utils.logger import get_logger, LoggerManager
from core.agent_components import AgentComponentBundle, AgentComponentFactory
from core.chat.message_handler import MessageHandler
from core.chat.skill_handlers import MarketAnalysisHandler, ShortDramaHandler
from core.autonomous.autonomous_loop import AutonomousLoop
import random


class AgentApplication:
    def __init__(self, ui_mode: str = "tkinter", autonomous: bool = False, initial_goal: Optional[str] = None):
        self.logger = get_logger("agent.application")
        self.config_loader = ConfigLoader()
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ui_mode = ui_mode
        self._autonomous_enabled = autonomous
        self._initial_goal = initial_goal

        self.c = AgentComponentFactory.create_all(self.config_loader, self.logger, ui_mode, kernel=self)
        self._ui_manager = self.c.ui_manager
        self._ui_module = self.c.ui_module

        self.msg_handler = MessageHandler(self.c, self.logger)
        self.market_handler = MarketAnalysisHandler(self.c, self.logger)
        self.drama_handler = ShortDramaHandler(self.c, self.logger)
        self.autonomous_loop = AutonomousLoop(self.c, self.logger, initial_goal)

        self._setup_callbacks()

    def _setup_callbacks(self) -> None:
        if self._ui_manager:
            self._ui_manager.set_emergency_callback(self._on_emergency_stop)
            self._ui_manager.set_resume_callback(self._on_resume)
            if hasattr(self._ui_manager, 'set_agents'):
                self._ui_manager.set_agents(
                    agent_manager=self.c.agent_manager, memory_manager=self.c.memory_manager,
                    curiosity_system=self.c.curiosity_system, safety_manager=self.c.safety_manager)
            if hasattr(self._ui_manager, 'set_chat_callback'):
                self._ui_manager.set_chat_callback(self._on_chat_message)

        self.c.perception_manager.on_window_change(self._on_window_change)
        self.c.perception_manager.on_clipboard_change(self._on_clipboard_change)
        if self.c.curiosity_system:
            self.c.curiosity_system.on_state_change(self._on_curiosity_change)
        self.c.safety_manager.register_stop_handler(self._on_system_stop)
        self.c.safety_manager.register_resume_handler(self._on_system_resume)

    def _on_chat_message(self, message: str) -> str:
        if any(kw in message for kw in ["市场调研", "市场分析", "行业分析", "市场报告"]):
            return self.market_handler.execute(message)
        if any(kw in message for kw in ["短剧", "剧本", "分镜"]):
            return self.drama_handler.execute(message)
        return self.msg_handler.handle(message)

    def _on_emergency_stop(self) -> None:
        self.logger.critical("用户触发急停")
        self.c.safety_manager.trigger_emergency_stop(level="user", source="user", message="用户点击急停按钮")
        if hasattr(self._ui_manager, 'set_emergency_state'):
            self._ui_manager.set_emergency_state(True)

    def _on_resume(self) -> None:
        self.logger.info("用户触发恢复")
        self.c.safety_manager.resume("user")
        if hasattr(self._ui_manager, 'set_emergency_state'):
            self._ui_manager.set_emergency_state(False)

    def _on_window_change(self, window_info) -> None:
        if hasattr(self._ui_manager, 'update_perception_panel'):
            self._ui_manager.update_perception_panel({'window': window_info.to_dict() if window_info else None})
        if window_info:
            result = self.c.safety_manager.validate_window(window_info.title)
            if not result.is_allowed:
                self.logger.warning(f"窗口被阻止: {window_info.title}")

    def _on_clipboard_change(self, content) -> None:
        if hasattr(self._ui_manager, 'update_perception_panel'):
            self._ui_manager.update_perception_panel({'clipboard': content.to_dict() if content else None})
        if content:
            result = self.c.safety_manager.validate_clipboard(content.content)
            if not result.is_allowed:
                self.logger.warning(f"剪贴板内容被阻止: {result.reason}")

    def _on_curiosity_change(self, state) -> None:
        if hasattr(self._ui_manager, 'update_curiosity_panel'):
            self._ui_manager.update_curiosity_panel(state.to_dict())

    def _on_system_stop(self) -> None:
        if hasattr(self._ui_manager, 'update_status'):
            self._ui_manager.update_status("系统已停止")
        if hasattr(self._ui_manager, 'set_emergency_state'):
            self._ui_manager.set_emergency_state(True)

    def _on_system_resume(self) -> None:
        if hasattr(self._ui_manager, 'update_status'):
            self._ui_manager.update_status("系统运行中")
        if hasattr(self._ui_manager, 'set_emergency_state'):
            self._ui_manager.set_emergency_state(False)

    async def print_full_data_chain(self, action_context: dict, decision=None, outcome=None):
        print("\n" + "=" * 100)
        print("小七 完整数据链输出")
        print("=" * 100)
        print(f"\n【1. 动作请求】\nAction Type : {action_context.get('action_type', 'unknown')}\nDetails     : {action_context}")
        if decision:
            print(f"\n【2. SafetyOS 决策】\nRisk Score      : {decision.risk_score:.3f}\nFinal Decision  : {decision.final_decision}\nReason          : {decision.reason}")
            if decision.triple_teacher_review:
                tr = decision.triple_teacher_review
                print(f"\n【3. 三老师审查 (对错观)】")
                fusion = tr.get('fusion_score', 'N/A')
                print(f"Fusion Score    : {fusion:.3f}" if isinstance(fusion, (int, float)) else f"Fusion Score    : {fusion}")
                print(f"Recommendation  : {tr.get('recommendation', 'N/A')}\nSummary         : {tr.get('summary', 'N/A')}")
        print(f"\n【4. 时间轴记录】")
        if hasattr(self, 'c') and self.c.safety_os:
            for e in self.c.safety_os.timeline.safety(limit=5)[-3:]:
                ts = str(e.get('ts', ''))[:19]
                print(f"  {ts} | {e.get('type', '')} | {e.get('final_decision', '')}")
        print(f"\n【5. 因果链】")
        if decision and hasattr(self, 'c') and self.c.safety_os:
            causal = self.c.safety_os.timeline.causal(decision.decision_id)
            print(f"Root Causes : {causal.get('causes', [])}\nEffects     : {causal.get('effects', [])}")
        print(f"\n【6. 认知OS 对错观 & Identity】")
        if hasattr(self, 'cognitive_kernel'):
            ck = self.cognitive_kernel
            if hasattr(ck, 'identity_core'):
                print(f"Current Identity : {str(getattr(ck.identity_core, 'current_state', 'N/A'))[:80]}...")
            if hasattr(ck, 'value_system') and hasattr(ck.value_system, 'get_alignment_score'):
                try: print(f"Value Alignment  : {ck.value_system.get_alignment_score(action_context)}")
                except: print(f"Value Alignment  : N/A")
        print(f"\n【7. 学习信号】\nOutcome Success   : {outcome.get('success', '待执行') if outcome else '待执行'}\nUser Intervention : {outcome.get('user_intervention', False) if outcome else 'N/A'}")
        print(f"\n【8. 漂移检测】")
        if hasattr(self, 'c') and self.c.safety_os:
            drift = self.c.safety_os.check_drift()
            print(f"漂移状态 : {drift.get('drift', False)}")
            if drift.get('drift_score') is not None: print(f"漂移分数 : {drift['drift_score']}")
            print(f"建议     : {drift.get('recommendation', 'N/A')}")
        print("\n" + "=" * 100 + "\n数据链输出完成\n" + "=" * 100)

    def list_data_chains(self, limit: int = 20):
        if not self.c.safety_os:
            print("[SafetyOS] 未初始化"); return []
        table = self.c.safety_os.data_chain_manager.list_capsules(limit=limit)
        print(f"\n=== 小七 数据链胶囊列表 (共 {len(table)} 条) ===")
        for row in table: print(row)
        return table

    def show_data_chain(self, capsule_id: str):
        if not self.c.safety_os:
            print("[SafetyOS] 未初始化"); return {}
        import json
        detail = self.c.safety_os.data_chain_manager.show(capsule_id)
        print(json.dumps(detail, ensure_ascii=False, indent=2))
        return detail

    async def approve_and_save(self, action_context: dict, execute_fn=None):
        if not self.c.safety_os:
            self.logger.warning("[SafetyOS] 未初始化，无法执行审批"); return {"decision": None, "outcome": None, "capsule_id": None}
        decision = await self.c.safety_os.approve(action_context)
        outcome = None
        if execute_fn and decision.final_decision == "allow":
            try:
                result = await execute_fn(action_context)
                outcome = {"success": True, "user_intervention": False, "result": result}
            except Exception as e:
                outcome = {"success": False, "user_intervention": False, "error": str(e)}
            await self.c.safety_os.record_outcome(decision, outcome)
        capsule_id = f"decision_{decision.decision_id[:8]}"
        self.logger.info(f"[小七] 审批完成: decision={decision.final_decision}, capsule≈{capsule_id}")
        return {"decision": decision, "outcome": outcome, "capsule_id": capsule_id}

    async def execute_with_golden_chain(self, action_context: dict, execute_fn=None):
        from datetime import datetime
        if not self.c.golden_chain_manager:
            self.logger.warning("[黄金数据链] 管理器未初始化"); return None
        perception = {"source": action_context.get("source", "user_or_env"), "timestamp": datetime.now().isoformat(), "raw_input": action_context.get("raw_input", str(action_context)[:200])}
        decision = await self.c.safety_os.approve(action_context)
        cognition = {"identity_state": getattr(self.c.identity_core, 'current_state', None), "value_alignment": None, "curiosity_score": getattr(self.c.curiosity_system, 'total_score', None) if self.c.curiosity_system else None}
        outcome = None
        if execute_fn and decision.final_decision == "allow":
            try:
                result = await execute_fn(action_context); outcome = {"success": True, "result": result, "user_intervention": False}
            except Exception as e:
                outcome = {"success": False, "error": str(e), "user_intervention": False}
            await self.c.safety_os.record_outcome(decision, outcome)
        memory_storage = {"stored_in": ["episodic", "semantic"], "capsule_ids": []}
        safety_audit = {"decision": decision.to_dict() if hasattr(decision, 'to_dict') else {"risk_score": decision.risk_score, "final_decision": decision.final_decision}, "triple_teacher": getattr(decision, 'triple_teacher_review', {})}
        behavior_output = {"executed_action": action_context.get("action_type", "unknown"), "decision": decision.final_decision, "outcome": outcome}
        from core.observation.reward_explainer import RewardExplainer
        reward_explainer = RewardExplainer()
        reward_explanation = reward_explainer.explain(decision={"final_decision": decision.final_decision, "risk_score": decision.risk_score}, teacher=getattr(decision, 'triple_teacher_review', {}), outcome=outcome)
        drift_info = self.c.safety_os.check_drift() if hasattr(self.c.safety_os, 'check_drift') else {}
        self_growth = {"learning_reward": reward_explanation["reward"], "reward_reason": reward_explanation["reason"], "reward_factors": reward_explanation["factors"], "alignment": reward_explanation["alignment"], "trainable_signal": reward_explanation["trainable_signal"], "drift_score": drift_info.get("drift_score", 0.0), "drift_detected": drift_info.get("drift", False)}
        golden_chain = self.c.golden_chain_manager.create_chain(perception=perception, cognition=cognition, memory_storage=memory_storage, safety_audit=safety_audit, behavior_output=behavior_output, self_growth=self_growth)
        self.logger.info(f"[小七] 黄金数据链已生成: {golden_chain.capsule_id}, trace={golden_chain.traceability_id}")
        return golden_chain

    def _update_ui_data(self) -> None:
        try:
            if hasattr(self._ui_manager, 'update_memory_panel'):
                self._ui_manager.update_memory_panel({
                    'exclusive': [item.to_dict() for item in self.c.memory_manager.exclusive_capsule.get_all(limit=10)],
                    'errors': [item.to_dict() for item in self.c.memory_manager.error_capsule.get_all(limit=10)],
                    'curiosity': [item.to_dict() for item in self.c.memory_manager.curiosity_capsule.get_all(limit=10)],
                    'skills': [item.to_dict() for item in self.c.memory_manager.skill_cache_capsule.get_all(limit=10)],
                    'short_term': [item.to_dict() for item in self.c.memory_manager.short_term_memory.get_all(limit=10)]})
            if hasattr(self._ui_manager, 'update_perception_panel'):
                self._ui_manager.update_perception_panel({'stats': self.c.perception_manager.get_system_stats(), 'process_count': len(self.c.perception_manager.process_monitor.get_watched())})
            if hasattr(self._ui_manager, 'update_agent_panel') and self.c.master_agent is not None:
                self._ui_manager.update_agent_panel(self.c.master_agent.get_status())
        except Exception as e:
            self.logger.error(f"更新UI数据失败: {e}")

    async def _async_main(self) -> None:
        self.logger.info("启动异步任务...")

        # Phase 7.5: 按 SAFE_ENABLE_ORDER 逐步启用模块
        # teaching_system(low) → curiosity_system(medium) → evolution_loop(high) → async_task(high) → loop_execution(high)
        self.c.module_switch.enable("teaching_system")
        self.c.module_switch.enable("curiosity_system")
        self.c.module_switch.enable("evolution_loop")
        self.c.module_switch.enable("async_task")
        self.c.module_switch.enable("loop_execution")
        self.logger.info(f"[Phase 7.5] ModuleSwitch 已启用: {self.c.module_switch.status()}")

        await self.c.perception_manager.start()
        await self.c.agent_manager.start()
        if self.c.master_agent is not None:
            await self.c.master_agent.start()
        if self.c.module_switch.is_enabled("curiosity_system") and self.c.curiosity_system is not None:
            self.c.curiosity_system.start()
        if self.c.module_switch.is_enabled("async_task") and self.c.master_agent is not None:
            asyncio.create_task(self.c.master_agent.run())
        if self.c.module_switch.is_enabled("async_task") and self._autonomous_enabled:
            self.autonomous_loop.running = True
            asyncio.create_task(self.autonomous_loop.run())
        if self.c.module_switch.is_enabled("loop_execution"):
            while self._running:
                await self.c.safety_manager.check_and_wait_async()
                self._update_ui_data()
                await asyncio.sleep(1.0)

    def _run_async_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            self.logger.error(f"异步循环错误: {e}")
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending: task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as e:
                self.logger.warning(f"清理任务时出错: {e}")
            self._loop.close()
            self.logger.info("[关闭] Event loop 已关闭")

    def start(self) -> int:
        self.logger.info("=" * 50 + "\nAgent 5.0 启动中...\nUI模式: " + self._ui_mode + "\n" + "=" * 50)
        self._running = True
        if self._ui_mode == "tkinter" and self._ui_module:
            deps = self._ui_module['check_dependencies']()
            missing = [k for k, v in deps.items() if not v]
            if missing:
                self.logger.warning(f"缺失依赖: {missing}")
                self._ui_module['print_dependency_status']()
                print(f"\n请安装缺失依赖: pip install {' '.join(missing)}")
                return 1
            root = float_win = None
            try:
                import tkinter as tk
                root = tk.Tk()
                main_win = self._ui_module['MainChatWindow'](root)
                self._ui_module['GLOBAL_STATE'].main_win = main_win
                self._ui_module['GLOBAL_STATE'].agent = self.c.master_agent
                main_win.bind_agent(self.c.master_agent)
                main_win.set_chat_callback(self._on_chat_message)
                self._ui_module['data_provider'].set_agent(self.c.master_agent)
                self._ui_module['data_provider'].start_push_mode(interval=3.0)
                float_root = tk.Toplevel(root)
                float_win = self._ui_module['FloatMonitorWindow'](float_root)
                self._ui_module['GLOBAL_STATE'].float_win = float_win
                self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
                self._thread.start()
                self.logger.info("Agent 5.0 启动完成")
                root.mainloop()
            except KeyboardInterrupt:
                self.logger.info("用户中断")
            except Exception as e:
                self.logger.error(f"启动失败: {e}")
                import traceback; traceback.print_exc()
            finally:
                self._cleanup_ui(root, float_win)
                self.stop()
            return 0
        if self._ui_manager:
            self._ui_manager.initialize()
            self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
            self._thread.start()
            if hasattr(self._ui_manager, 'update_status'):
                self._ui_manager.update_status("系统运行中")
            self.logger.info("Agent 5.0 启动完成")
            exit_code = self._ui_manager.run()
            self.stop()
            return exit_code
        return 0

    def _cleanup_ui(self, root, float_win) -> None:
        try:
            if self._ui_module:
                self._ui_module['data_provider'].stop_push_mode()
                self._ui_module['GLOBAL_STATE'].shutdown_flag = True
                try:
                    import matplotlib.pyplot as plt; plt.close('all')
                except: pass
                if float_win:
                    try:
                        if hasattr(float_win, 'cleanup'): float_win.cleanup()
                        if hasattr(float_win, 'root') and float_win.root: float_win.root.quit(); float_win.root.destroy()
                    except Exception as e: self.logger.debug(f"清理悬浮窗失败: {e}")
                if root:
                    try: root.quit(); root.destroy()
                    except Exception as e: self.logger.debug(f"清理主窗口失败: {e}")
                if self.c.memory_manager:
                    try: self.c.memory_manager.close()
                    except Exception as e: self.logger.debug(f"关闭记忆管理器失败: {e}")
                self.logger.info("UI 资源清理完成")
        except Exception as e:
            self.logger.error(f"清理 UI 失败: {e}")

    def stop(self) -> None:
        self.logger.info("Agent 5.0 停止中...")
        self._running = False
        self.autonomous_loop.running = False
        if self._ui_mode == "tkinter" and self._ui_module:
            self._ui_module['data_provider'].stop_push_mode()
            self._ui_module['GLOBAL_STATE'].shutdown_flag = True
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._shutdown_async(), self._loop)
            try: future.result(timeout=10.0)
            except Exception as e: self.logger.warning(f"异步关闭超时: {e}")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.logger.info("Agent 5.0 已停止")

    async def _shutdown_async(self) -> None:
        self.logger.info("开始异步组件关闭...")
        for name, comp, is_async in [
            ("MasterAgent", self.c.master_agent, True), ("PerceptionManager", self.c.perception_manager, True),
            ("AgentManager", self.c.agent_manager, True), ("CuriositySystem", self.c.curiosity_system, False)]:
            try:
                if comp is not None and hasattr(comp, 'stop'):
                    await comp.stop() if is_async else comp.stop()
                    self.logger.info(f"[关闭] {name} 已停止")
            except Exception as e:
                self.logger.error(f"[关闭] {name} 停止失败: {e}")
        try:
            self.c.memory_manager.close()
            self.logger.info("[关闭] MemoryManager 已关闭")
        except Exception as e:
            self.logger.error(f"[关闭] MemoryManager 关闭失败: {e}")
        LoggerManager().close_all()


def main():
    parser = argparse.ArgumentParser(description="Agent 5.0 AI智能代理系统")
    parser.add_argument("--ui", "-u", choices=["pyqt", "tkinter"], default="tkinter", help="UI模式")
    parser.add_argument("--test", "-t", action="store_true", help="运行集成测试")
    parser.add_argument("--autonomous", "-a", action="store_true", help="启用自主循环模式")
    parser.add_argument("--goal", "-g", type=str, default=None, help="设置初始目标")
    args = parser.parse_args()

    if args.test:
        import unittest
        from tests import test_integration, test_memory, test_perception, test_curiosity
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for mod in [test_integration, test_memory, test_perception, test_curiosity]:
            suite.addTests(loader.loadTestsFromModule(mod))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    app = AgentApplication(ui_mode=args.ui, autonomous=args.autonomous, initial_goal=args.goal)

    def signal_handler(signum, frame):
        get_logger("main").info(f"收到信号 {signum}，正在关闭...")
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    return app.start()


if __name__ == "__main__":
    sys.exit(main())
