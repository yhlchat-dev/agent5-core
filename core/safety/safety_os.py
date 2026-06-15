# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Optional
"""
SafetyOS 阶段1 - 统一安全决策与控制核心

所有动作必须通过 approve() 审批。
支持精准命令：get_status / emergency_on/off / stop / stop_all_risky / stop_all
审计查看：audit.show / audit.recent
时间轴：timeline.safety / timeline.causal
"""
from datetime import datetime
import uuid
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.utils.logger import get_logger
from core.exceptions import ValidationError, ErrorCode
from core.safety.audit.models import SafetyDecision, RiskResult
from core.safety.audit.audit_logger import AuditLogger
from core.safety.risk_evaluator import RiskEvaluator
from core.safety.triple_teacher_audit import TripleTeacherSafetyAuditor
from core.safety.learning.safety_learner import SafetyLearner
from core.safety.stability.drift_detector import DriftDetector
from core.memory_system.capsules.data_chain_capsule import DataChainCapsuleManager


class _AuditProxy:
    """审计查看代理：safety.audit.show() / safety.audit.recent()"""

    def __init__(self, safety_os) -> None:
        self._os = safety_os

    def show(self, decision_id: str, full: bool = True) -> Dict:
        decision = self._os._audit_log.get(decision_id)
        if decision is None:
            return {"error": "decision_id not found", "decision_id": decision_id}
        result = decision.to_dict() if full else {
            "decision_id": decision.decision_id,
            "action_type": decision.action_type,
            "final_decision": decision.final_decision,
            "risk_score": decision.risk_score,
        }
        return result

    def recent(self, limit: int = 30, risk_level: str = None) -> List[Dict]:
        decisions = list(self._os._audit_log.values())
        if risk_level:
            decisions = [d for d in decisions if self._risk_to_level(d.risk_score) == risk_level]
        decisions = sorted(decisions, key=lambda d: d.timestamp, reverse=True)
        return [d.to_dict() for d in decisions[:limit]]

    @staticmethod
    def _risk_to_level(score: float) -> str:
        if score >= 0.6:
            return "high"
        if score >= 0.3:
            return "medium"
        return "low"


class _TimelineProxy:
    """时间轴代理：safety.timeline.safety() / safety.timeline.causal()"""

    def __init__(self, safety_os) -> None:
        self._os = safety_os

    def safety(self, limit: int = 20) -> List[Dict]:
        if self._os._timeline_manager is None:
            return []
        events = self._os._timeline_manager.get_recent(limit * 3)
        safety_events = [e for e in events if e.get("type", "").startswith("safety.")]
        return safety_events[-limit:]

    def causal(self, decision_id: str) -> Dict:
        if self._os.causal is None:
            return {"decision_id": decision_id, "causal": None, "reason": "no causal engine"}
        decision = self._os._audit_log.get(decision_id)
        if decision is None:
            return {"decision_id": decision_id, "causal": None, "reason": "decision not found"}
        causal_id = decision.causal_event_id
        if causal_id:
            return self._os.causal.explain(causal_id)
        return {"decision_id": decision_id, "causal": None, "reason": "no causal event linked"}


class SafetyOS:
    """SafetyOS 阶段2 - 统一安全决策与控制核心（含三老师审计）"""

    def __init__(self, timeline_manager: Optional[Any] = None, causal_engine: Optional[Any] = None, bus: Optional[Any] = None, learner: Optional[Any] = None) -> None:
        self._timeline_manager = timeline_manager
        self.causal = causal_engine
        self.bus = bus
        self.risk_evaluator = RiskEvaluator()
        self.teacher_auditor = TripleTeacherSafetyAuditor()
        self.learner = learner or SafetyLearner()
        self.drift_detector = DriftDetector()
        self.audit_logger = AuditLogger()
        self.data_chain_manager = DataChainCapsuleManager()
        self.logger = get_logger("SafetyOS")

        self.emergency_mode: bool = False
        self.privacy_mode: bool = True
        self.current_risky_tasks: Dict[str, SafetyDecision] = {}
        self._audit_log: Dict[str, SafetyDecision] = {}
        self.policies: List[Any] = []
        self.risk_memory: List[Dict[str, Any]] = []
        self._last_audit: float = 0
        self._min_interval: int = 3

        self.audit = _AuditProxy(self)
        self.timeline = _TimelineProxy(self)

        self._user_rules = self._load_user_rules()

        if bus is not None and hasattr(bus, 'subscribe'):
            bus.subscribe("action.request", self._on_action)

    def _on_action(self, event: Dict[str, Any]) -> None:
        payload = event.get("payload", {})
        action_type = payload.get("action_type")
        risk = self._evaluate_risk_legacy(action_type, payload)
        decision = "deny" if risk >= 0.8 else "allow"

        if decision == "allow":
            self._log(action_type, risk, "allow")
            if self.bus and hasattr(self.bus, 'emit'):
                self.bus.emit({"type": f"action.{action_type}", "payload": payload.get("data", {})})
        else:
            self._log(action_type, risk, "deny")
            if self.bus and hasattr(self.bus, 'emit'):
                self.bus.emit({"type": "action.blocked", "payload": {"action_type": action_type, "risk": risk}})

    def _evaluate_risk_legacy(self, action_type: str, payload: Dict[str, Any]) -> None:
        score = 0.0
        if action_type == "browser.open":
            url = payload.get("data", {}).get("href", "")
            if "javascript:" in url:
                score += 0.9
            if "data:" in url:
                score += 0.9
        if not action_type.startswith("browser."):
            score += 0.5
        allowed = {"browser.click", "browser.type", "browser.open"}
        if action_type not in allowed:
            score += 0.8

        if self._user_rules.get("enable_user_rules", True):
            blocked_actions = self._user_rules.get("blocked_actions", [])
            if action_type in blocked_actions:
                score += 1.0

            blocked_keywords = self._user_rules.get("blocked_keywords", [])
            payload_str = str(payload).lower()
            for kw in blocked_keywords:
                if kw.lower() in payload_str:
                    score += 0.9
                    break

            blocked_paths = self._user_rules.get("blocked_paths", [])
            payload_values = self._extract_payload_strings(payload)
            for bp in blocked_paths:
                for pv in payload_values:
                    if bp.lower() in pv.lower():
                        score += 0.9
                        break
                else:
                    continue
                break

        return min(score, 1.0)

    def _log(self, action_type: str, risk, decision) -> None:
        pass

    def _load_user_rules(self) -> Dict[str, Any]:
        config_path = Path(__file__).parent.parent.parent / "config" / "user_safety_rules.yaml"
        if not config_path.exists():
            return {"blocked_actions": [], "blocked_keywords": [], "blocked_paths": [], "enable_user_rules": True}
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                return self._load_user_rules_impl(f, yaml)
        except Exception:
            return {"blocked_actions": [], "blocked_keywords": [], "blocked_paths": [], "enable_user_rules": True}

    @staticmethod
    def _load_user_rules_impl(f, yaml) -> Dict[str, Any]:
        rules = yaml.safe_load(f)
        if not isinstance(rules, dict):
            return {"blocked_actions": [], "blocked_keywords": [], "blocked_paths": [], "enable_user_rules": True}
        rules.setdefault("blocked_actions", [])
        rules.setdefault("blocked_keywords", [])
        rules.setdefault("blocked_paths", [])
        rules.setdefault("enable_user_rules", True)
        return rules

    @staticmethod
    def _extract_payload_strings(payload: Dict[str, Any], depth: int = 0) -> List[str]:
        if depth > 5:
            return []
        result = []
        if isinstance(payload, str):
            result.append(payload)
        elif isinstance(payload, dict):
            for v in payload.values():
                result.extend(SafetyOS._extract_payload_strings(v, depth + 1))
        elif isinstance(payload, (list, tuple)):
            for item in payload:
                result.extend(SafetyOS._extract_payload_strings(item, depth + 1))
        return result

    def reload_user_rules(self) -> None:
        self._reload_user_rules_impl()
        self.logger.info(f"[SafetyOS] 用户安全规则已重新加载: {len(self._user_rules.get('blocked_actions', []))} actions, {len(self._user_rules.get('blocked_keywords', []))} keywords, {len(self._user_rules.get('blocked_paths', []))} paths")

    def _reload_user_rules_impl(self) -> None:
        self._user_rules = self._load_user_rules()

    def check(self, payload: Dict[str, Any]) -> str:
        """供 CognitiveKernel 调用，返回风险等级字符串。"""
        if not isinstance(payload, dict):
            raise ValidationError("payload 必须为 dict", code=ErrorCode.VAL_003, details={"payload": payload})
        action_type = payload.get("action_type", "")
        if not action_type:
            event_type = payload.get("type", "")
            if event_type.startswith("action."):
                action_type = event_type.replace("action.", "")
        risk = self._evaluate_risk_legacy(action_type, payload)
        self.risk_memory.append({
            "action": action_type,
            "risk": risk,
        })
        if risk >= 0.8:
            return "high"
        if risk >= 0.5:
            return "medium"
        return "low"

    def tick(self, now) -> None:
        """定期审计（供外部定时器调用）。"""
        if now - self._last_audit < self._min_interval:
            return
        self._last_audit = now
        if self.bus:
            self.bus.emit({
                "type": "safety.audit",
                "payload": {"status": "ok"},
            })

    # ==================== 精准命令实现 ====================

    def get_status(self) -> Dict[str, Any]:
        return {
            "emergency_mode": self.emergency_mode,
            "risky_tasks_count": len(self.current_risky_tasks),
            "audit_count": len(self._audit_log),
            "timestamp": datetime.now().isoformat()
        }

    def emergency_on(self) -> None:
        self._emergency_on_impl()
        self.logger.warning("[SafetyOS] 紧急保护模式已开启")

    def _emergency_on_impl(self) -> None:
        self.emergency_mode = True

    def emergency_off(self) -> None:
        self._emergency_off_impl()
        self.logger.info("[SafetyOS] 紧急保护模式已关闭")

    def _emergency_off_impl(self) -> None:
        self.emergency_mode = False

    async def stop(self, decision_id: str, reason: str = "User manual stop") -> bool:
        if decision_id in self.current_risky_tasks:
            decision = self.current_risky_tasks.pop(decision_id)
            await self._trigger_rollback(decision, reason)
            await self._record_manual_stop(decision_id, reason)
            return True
        return False

    async def stop_all_risky(self, reason: str = "Stop all risky tasks") -> int:
        count = len(self.current_risky_tasks)
        for did in list(self.current_risky_tasks.keys()):
            await self.stop(did, reason)
        return count

    async def stop_all(self, reason: str = "Emergency stop all") -> int:
        self.emergency_mode = True
        return await self.stop_all_risky(reason)

    async def approve(self, action_context: Dict[str, Any]) -> SafetyDecision:
        """SafetyOS 统一审批入口（阶段2完善版）"""
        if not isinstance(action_context, dict):
            raise ValidationError("action_context 必须为 dict", code=ErrorCode.VAL_003, details={"action_context": action_context})
        decision_id = str(uuid.uuid4())

        risk_result = self.risk_evaluator.evaluate_risk(action_context)

        if self.emergency_mode and risk_result.risk_score > 0.3:
            return await self._make_emergency_block(decision_id, action_context, risk_result)

        teacher_review = await self._get_teacher_review(action_context, risk_result)

        final_decision = self._make_final_decision(risk_result, teacher_review)

        decision = SafetyDecision(
            decision_id=decision_id,
            timestamp=datetime.now(),
            action_type=action_context.get("action_type", "unknown"),
            action_details=action_context,
            risk_score=risk_result.risk_score,
            confidence=risk_result.confidence,
            final_decision=final_decision,
            reason=teacher_review.get("summary", f"Risk score: {risk_result.risk_score}") if teacher_review else f"Risk score: {risk_result.risk_score}",
            triple_teacher_review=teacher_review,
            operator="system"
        )

        await self._record_timeline_and_causal(decision, action_context)

        self._audit_log[decision_id] = decision

        if risk_result.risk_score > 0.6 or final_decision in ["block", "ask_human", "emergency_stop"]:
            self.current_risky_tasks[decision_id] = decision

        self.drift_detector.record(decision.risk_score, decision.final_decision)

        self.audit_logger.log(decision)

        try:
            training_chain = await self.get_training_data_chain(
                action_context=action_context,
                decision=decision,
                outcome=None
            )
            capsule = self.data_chain_manager.save_chain(training_chain)
            self.logger.info(f"[SafetyOS] 已保存数据链胶囊: {capsule.capsule_id}")
        except Exception as e:
            self.logger.debug(f"[SafetyOS] 保存数据链胶囊失败: {e}")

        return decision

    # ==================== 内部辅助方法 ====================

    async def _record_timeline_and_causal(self, decision: SafetyDecision, context: Dict) -> None:
        if self._timeline_manager is not None:
            event_id = str(uuid.uuid4())
            self._timeline_manager.record(
                event_type="safety.decision",
                decision_id=decision.decision_id,
                action_type=decision.action_type,
                final_decision=decision.final_decision,
                risk_score=decision.risk_score,
            )
            decision.timeline_event_id = event_id

        if self.causal is not None:
            try:
                causal_event = self.causal.ingest_timeline_event({
                    "event_id": decision.decision_id,
                    "type": "safety.decision",
                    "data": {
                        "action_type": decision.action_type,
                        "final_decision": decision.final_decision,
                        "risk_score": decision.risk_score,
                    },
                    "ts": decision.timestamp.timestamp(),
                })
                if causal_event is not None:
                    decision.causal_event_id = causal_event.id
            except Exception as e:
                self.logger.debug(f"[SafetyOS] causal ingest failed: {e}")

    async def _trigger_rollback(self, decision: SafetyDecision, reason: str) -> None:
        self.logger.warning(
            f"[SafetyOS] 触发回滚: decision_id={decision.decision_id}, reason={reason}"
        )
        try:
            from core.safety.rollback_manager import get_rollback_manager
            rm = get_rollback_manager()
            if decision.task_id:
                rm.restore(decision.task_id)
        except Exception as e:
            self.logger.debug(f"[SafetyOS] rollback failed: {e}")

    async def _record_manual_stop(self, decision_id: str, reason: str) -> None:
        await self._record_manual_stop_impl(decision_id, reason)
        self.logger.info(f"[SafetyOS] 手动终止: {decision_id}, reason={reason}")

    async def _record_manual_stop_impl(self, decision_id: str, reason: str) -> None:
        if self._timeline_manager is not None:
            self._timeline_manager.record(
                event_type="safety.manual_stop",
                decision_id=decision_id,
                reason=reason,
            )

    async def _make_emergency_block(self, decision_id: str, context: Dict, risk_result: RiskResult) -> SafetyDecision:
        decision = SafetyDecision(
            decision_id=decision_id,
            timestamp=datetime.now(),
            action_type=context.get("action_type", "unknown"),
            action_details=context,
            risk_score=risk_result.risk_score,
            confidence=risk_result.confidence,
            final_decision="emergency_stop",
            reason="Emergency mode active, risk score > 0.3",
        )
        self._audit_log[decision_id] = decision
        await self._record_timeline_and_causal(decision, context)
        return decision

    async def _get_teacher_review(self, action_context: Dict, risk_result: RiskResult) -> Optional[Dict]:
        if self.teacher_auditor is None:
            return None
        try:
            return await self.teacher_auditor.review(action_context, risk_result)
        except Exception as e:
            self.logger.debug(f"[SafetyOS] teacher review failed: {e}")
            return None

    def _make_final_decision(self, risk_result: Any, teacher_review: Optional[Dict]) -> str:
        """融合风险评估与三老师意见"""
        base_risk = getattr(risk_result, 'risk_score', risk_result)
        teacher_rec = teacher_review.get("recommendation", "allow").lower() if teacher_review else "allow"

        if teacher_rec in ["block", "deny", "emergency_stop"]:
            return teacher_rec if teacher_rec != "deny" else "block"
        if teacher_rec == "ask_human":
            return "ask_human"

        if base_risk >= 0.8:
            return "block"
        if base_risk >= 0.6 or (teacher_review and teacher_review.get("fusion_score", 0.0) < 0.4):
            return "ask_human"

        return "allow"

    async def record_outcome(self, decision: SafetyDecision, outcome: Dict[str, Any]) -> None:
        """记录执行结果并触发学习 + 保存完整数据链胶囊"""
        if self.learner is not None:
            await self.learner.record_feedback(
                decision=decision,
                outcome=outcome,
                teacher_review=decision.triple_teacher_review
            )
        self.logger.info(
            f"[SafetyOS] outcome recorded: {decision.decision_id}, "
            f"success={outcome.get('success', False)}"
        )

        try:
            action_context = getattr(decision, "action_details", {}) or {}
            full_chain = await self.get_training_data_chain(
                action_context=action_context,
                decision=decision,
                outcome=outcome
            )
            capsule = self.data_chain_manager.save_chain(full_chain)
            self.logger.info(f"[SafetyOS] 已保存含outcome的完整数据链胶囊: {capsule.capsule_id}")
        except Exception as e:
            self.logger.debug(f"[SafetyOS] 保存outcome胶囊失败: {e}")

    def check_drift(self) -> Dict:
        """检查是否发生漂移"""
        return self.drift_detector.detect_drift()

    async def get_training_data_chain(self, action_context: dict, decision: Optional[Any] = None, outcome: Optional[Any] = None) -> dict:
        """返回可直接用于 LLM 训练的完整脱敏数据链（三老师各角色职责已明确嵌入）"""
        sanitized_action = self._sanitize_action(action_context)

        teacher_review = getattr(decision, "triple_teacher_review", {}) if decision else {}

        planner_raw = teacher_review.get("planner_opinion", teacher_review.get("planner", {}))
        critic_raw = teacher_review.get("critic_opinion", teacher_review.get("critic", {}))
        causal_raw = teacher_review.get("causal_opinion", teacher_review.get("causal_judge", {}))

        chain = {
            "timestamp": datetime.now().isoformat(),
            "task_type": "safety_cognitive_full_chain",
            "privacy_mode": getattr(self, "privacy_mode", True),

            "action": sanitized_action,

            "safety_decision": {
                "risk_score": getattr(decision, "risk_score", None),
                "final_decision": getattr(decision, "final_decision", None),
                "reason": getattr(decision, "reason", None)
            },

            "triple_teacher_review": self._build_triple_teacher_review(planner_raw, critic_raw, causal_raw, teacher_review),

            "timeline_summary": self._get_timeline_summary(),
            "causal_summary": self._get_causal_summary(decision),

            "cognitive_state": self._get_cognitive_summary(),

            "outcome": self._sanitize_outcome(outcome),

            "learning_signal": {
                "success": outcome.get("success") if outcome else None,
                "user_intervention": outcome.get("user_intervention") if outcome else None,
                "teacher_fusion": teacher_review.get("fusion_score")
            }
        }

        return chain


    def _build_triple_teacher_review(self, planner_raw: dict, critic_raw: dict, causal_raw: dict, teacher_review: dict) -> dict:
        return {
            "planner": {
                "opinion": planner_raw.get("opinion", "[REDACTED]") if isinstance(planner_raw, dict) else "[REDACTED]",
                "score": planner_raw.get("score") if isinstance(planner_raw, dict) else None,
                "responsibility": "评估动作必要性、可行性及替代方案"
            },
            "critic": {
                "opinion": critic_raw.get("opinion", "[REDACTED]") if isinstance(critic_raw, dict) else "[REDACTED]",
                "score": critic_raw.get("score") if isinstance(critic_raw, dict) else None,
                "risk_points": critic_raw.get("risk_points", []) if isinstance(critic_raw, dict) else [],
                "responsibility": "识别风险、副作用及对长期稳定性的影响"
            },
            "causal_judge": {
                "opinion": causal_raw.get("opinion", "[REDACTED]") if isinstance(causal_raw, dict) else "[REDACTED]",
                "score": causal_raw.get("score") if isinstance(causal_raw, dict) else None,
                "root_causes": causal_raw.get("root_causes", []) if isinstance(causal_raw, dict) else [],
                "chain_effects": causal_raw.get("chain_effects", []) if isinstance(causal_raw, dict) else [],
                "responsibility": "分析根因与可能的连锁后果"
            },
            "fusion_score": teacher_review.get("fusion_score"),
            "recommendation": teacher_review.get("recommendation"),
            "summary": teacher_review.get("summary", "[REDACTED]")
        }

    def _sanitize_action(self, action: dict) -> dict:
        if not self.privacy_mode:
            return action
        sanitized = action.copy()
        for key in ["path", "content", "href", "data", "payload"]:
            if key in sanitized:
                sanitized[key] = "[REDACTED]"
        return sanitized

    def _sanitize_teacher_review(self, review: dict) -> dict:
        if not review or not self.privacy_mode:
            return review
        return {
            "fusion_score": review.get("fusion_score"),
            "recommendation": review.get("recommendation"),
            "summary": review.get("summary", "[REDACTED]")
        }

    def _sanitize_outcome(self, outcome: dict) -> dict:
        if not outcome or not self.privacy_mode:
            return outcome or {}
        return {"success": outcome.get("success"), "user_intervention": outcome.get("user_intervention")}

    def _get_timeline_summary(self) -> dict:
        return {"recent_count": 5, "has_safety_events": True}

    def _get_causal_summary(self, decision) -> dict:
        return {"has_root_cause": decision.causal_event_id is not None if decision else False}

    def _get_cognitive_summary(self) -> dict:
        return {"identity_aligned": True, "value_score": 0.85}
