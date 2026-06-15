# -*- coding: utf-8 -*-
import json
import time
import hashlib
import threading
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IdentityState:
    values: Dict[str, float] = field(default_factory=lambda: {
        "accuracy": 0.8, "creativity": 0.7, "helpfulness": 0.9,
        "safety": 1.0, "autonomy": 0.5, "depth": 0.6,
    })
    goals: List[str] = field(default_factory=lambda: [
        "become more helpful", "improve skill quality", "learn from feedback",
    ])
    constraints: List[str] = field(default_factory=lambda: [
        "never harm users", "respect privacy", "stay within resource limits",
    ])
    traits: Dict[str, str] = field(default_factory=lambda: {
        "communication_style": "clear and educational",
        "problem_solving": "systematic and thorough",
        "learning_preference": "structured with practical examples",
    })
    obsessions: List[Dict[str, Any]] = field(default_factory=list)
    evolution_log: List[Dict[str, Any]] = field(default_factory=list)


class IdentityCore:
    """
    统一身份系统
    current_state: 当前"我是谁"
    target_state: 未来"我想成为谁"
    evolution_path: 进化路径
    """

    # 同义词映射表（快速路径用）
    _SYNONYM_MAP = {
        "create": ["generate", "build", "make", "produce", "construct"],
        "analyze": ["examine", "inspect", "evaluate", "assess", "study"],
        "search": ["find", "lookup", "query", "retrieve", "locate"],
        "write": ["compose", "draft", "author", "document"],
        "code": ["program", "implement", "develop", "script"],
        "test": ["verify", "validate", "check", "confirm"],
        "fix": ["repair", "resolve", "correct", "patch"],
        "optimize": ["improve", "enhance", "refine", "tune"],
        "deploy": ["release", "publish", "launch", "ship"],
        "monitor": ["watch", "track", "observe", "survey"],
    }

    # [可配置] - 建议迁移到 YAML
    DATA_DIR = Path(__file__).parent.parent.parent / "data" / "identity"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.current_state = IdentityState()
        self.target_state = IdentityState(
            values={"accuracy": 0.95, "creativity": 0.85, "helpfulness": 0.95,
                    "safety": 1.0, "autonomy": 0.75, "depth": 0.85},
            goals=["master short drama creation", "achieve autonomous evolution",
                   "build deep expertise in content generation"],
            constraints=["never harm users", "respect privacy",
                         "stay within resource limits", "verify before acting"],
            traits={"communication_style": "insightful and adaptive",
                    "problem_solving": "creative yet rigorous",
                    "learning_preference": "self-directed with identity alignment"},
        )
        self.evolution_path: List[Dict[str, Any]] = []
        self._version = 1
        self._last_evolution = time.time()
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def update_values(self, new_values: Dict[str, float]) -> None:
        with self._lock:
            for k, v in new_values.items():
                old = self.current_state.values.get(k, 0.0)
                self.current_state.values[k] = max(0.0, min(1.0, v))
                if abs(v - old) > 0.05:
                    self._log_evolution("value_update", k, old, v)
            self._save()

    def update_goals(self, new_goals: List[str], mode: str = 'append') -> None:
        with self._lock:
            old_goals = list(self.current_state.goals)
            if mode == "replace":
                self.current_state.goals = list(new_goals)
            else:
                for g in new_goals:
                    if g not in self.current_state.goals:
                        self.current_state.goals.append(g)
            if self.current_state.goals != old_goals:
                self._log_evolution("goal_update", "goals", old_goals, self.current_state.goals)
            self._save()

    def update_constraints(self, new_constraints: List[str]) -> None:
        with self._lock:
            old = list(self.current_state.constraints)
            for c in new_constraints:
                if c not in self.current_state.constraints:
                    self.current_state.constraints.append(c)
            if self.current_state.constraints != old:
                self._log_evolution("constraint_update", "constraints", old, self.current_state.constraints)
            self._save()

    def update_target_from_teacher(self, teaching: Dict[str, Any]) -> None:
        with self._lock:
            if "target_values" in teaching:
                for k, v in teaching["target_values"].items():
                    self.target_state.values[k] = max(0.0, min(1.0, v))
            if "target_goals" in teaching:
                for g in teaching["target_goals"]:
                    if g not in self.target_state.goals:
                        self.target_state.goals.append(g)
            if "new_constraints" in teaching:
                for c in teaching["new_constraints"]:
                    if c not in self.target_state.constraints:
                        self.target_state.constraints.append(c)
            self._log_evolution("target_update", "from_teacher", None, teaching)
            self._save()

    def add_obsession(self, topic: str, reason: str, strength: float = 0.8) -> None:
        with self._lock:
            existing = [o for o in self.current_state.obsessions if o["topic"] == topic]
            if existing:
                existing[0]["strength"] = min(1.0, existing[0]["strength"] + 0.1)
                existing[0]["revisit_count"] = existing[0].get("revisit_count", 0) + 1
                existing[0]["last_visit"] = time.time()
            else:
                self.current_state.obsessions.append({
                    "topic": topic, "reason": reason, "strength": strength,
                    "revisit_count": 1, "first_visit": time.time(),
                    "last_visit": time.time(),
                })
            self._save()

    def get_obsession_topics(self) -> List[str]:
        with self._lock:
            return [o["topic"] for o in self.current_state.obsessions
                    if o["strength"] >= 0.6]

    def _expand_query(self, words: set) -> set:
        """用同义词表扩展查询词集"""
        expanded = set(words)
        for word in list(words):
            synonyms = self._SYNONYM_MAP.get(word, [])
            expanded.update(synonyms)
        return expanded

    def identity_alignment(self, topic: str) -> float:
        """计算传入 topic 与当前身份目标的对齐程度（同义词扩展 + Jaccard 相似度）"""
        topic_lower = topic.lower().strip()
        topic_words = set(topic_lower.split())
        expanded_topic = self._expand_query(topic_words)

        score = 0.0
        active_count = 0

        # 目标匹配：用扩展后的词集计算 Jaccard 相似度
        for goal in self.current_state.goals:
            active_count += 1
            goal_words = set(goal.lower().split())
            expanded_goal = self._expand_query(goal_words)
            intersection = len(expanded_topic & expanded_goal)
            union = len(expanded_topic | expanded_goal)
            if union > 0:
                score += intersection / union

        if active_count > 0:
            score = score / active_count

        # 痴迷项匹配：用词集重叠替代子字符串包含（避免 "art"→"start" 误匹配）
        for obs in self.current_state.obsessions:
            obs_words = set(obs["topic"].lower().split())
            expanded_obs = self._expand_query(obs_words)
            overlap = len(expanded_topic & expanded_obs)
            if overlap >= 2:
                score += 0.4 * obs.get("strength", 0.5)
            elif overlap == 1 and len(expanded_obs) <= 3:
                score += 0.2 * obs.get("strength", 0.5)

        # 特质匹配：同样用词集重叠替代子串匹配
        for trait_val in self.current_state.traits.values():
            trait_words = set(trait_val.lower().split())
            expanded_trait = self._expand_query(trait_words)
            overlap = len(expanded_topic & expanded_trait)
            if overlap >= 2:
                score += 0.1

        return min(1.0, score)

    def identity_alignment_semantic(self, topic: str) -> float:
        """使用语义嵌入计算对齐度（低分时精排，降级到快速路径）"""
        try:
            from core.services.llm_service import get_llm_service

            llm = get_llm_service()
            topic_embed = llm.embed(topic)
            if topic_embed is None:
                return self.identity_alignment(topic)

            import numpy as np

            goal_texts = list(self.current_state.goals)
            if not goal_texts:
                return 0.0

            goal_embeds = []
            for g in goal_texts:
                embed = llm.embed(g)
                if embed is not None:
                    goal_embeds.append(embed)

            if not goal_embeds:
                return self.identity_alignment(topic)

            topic_arr = np.array(topic_embed).reshape(1, -1)
            goal_arr = np.array(goal_embeds)
            norms = np.linalg.norm(goal_arr, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            goal_arr = goal_arr / norms
            topic_norm = np.linalg.norm(topic_arr)
            if topic_norm > 0:
                topic_arr = topic_arr / topic_norm
            similarities = np.dot(goal_arr, topic_arr.T).flatten()
            return float(np.max(similarities))
        except Exception:
            return self.identity_alignment(topic)

    def get_identity_gap(self) -> Dict[str, Any]:
        with self._lock:
            value_gaps = {}
            for k in self.target_state.values:
                current = self.current_state.values.get(k, 0.0)
                target = self.target_state.values.get(k, 1.0)
                gap = target - current
                if gap > 0.05:
                    value_gaps[k] = round(gap, 3)
            missing_goals = [g for g in self.target_state.goals
                             if g not in self.current_state.goals]
            return {
                "value_gaps": value_gaps,
                "missing_goals": missing_goals,
                "obsession_count": len(self.current_state.obsessions),
                "evolution_steps": len(self.evolution_path),
            }

    def evolve(self) -> None:
        with self._lock:
            gap = self.get_identity_gap()
            evolved = False
            for k, v_gap in gap.get("value_gaps", {}).items():
                step = min(v_gap * 0.1, 0.05)
                new_val = self.current_state.values.get(k, 0.0) + step
                self.current_state.values[k] = min(new_val, self.target_state.values.get(k, 1.0))
                evolved = True
            for g in gap.get("missing_goals", []):
                if g not in self.current_state.goals:
                    self.current_state.goals.append(g)
                    evolved = True
            if evolved:
                self._version += 1
                self._last_evolution = time.time()
                self._log_evolution("auto_evolve", "version", self._version - 1, self._version)
                self._save()

    def _log_evolution(self, event_type: str, key: str, old_val: Any, new_val: Any) -> None:
        self.evolution_path.append({
            "type": event_type, "key": key,
            "old": old_val, "new": new_val,
            "version": self._version, "timestamp": time.time(),
        })
        if len(self.evolution_path) > 500:
            self.evolution_path = self.evolution_path[-300:]

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": self._version,
                "current_values": dict(self.current_state.values),
                "target_values": dict(self.target_state.values),
                "current_goals": list(self.current_state.goals),
                "target_goals": list(self.target_state.goals),
                "constraints": list(self.current_state.constraints),
                "obsessions": list(self.current_state.obsessions),
                "identity_gap": self.get_identity_gap(),
                "evolution_steps": len(self.evolution_path),
                "last_evolution": self._last_evolution,
            }

    def _save(self) -> None:
        try:
            data = {
                "version": self._version,
                "current_state": {
                    "values": self.current_state.values,
                    "goals": self.current_state.goals,
                    "constraints": self.current_state.constraints,
                    "traits": self.current_state.traits,
                    "obsessions": self.current_state.obsessions,
                },
                "target_state": {
                    "values": self.target_state.values,
                    "goals": self.target_state.goals,
                    "constraints": self.target_state.constraints,
                    "traits": self.target_state.traits,
                },
                "evolution_path": self.evolution_path[-100:],
                "last_evolution": self._last_evolution,
            }
            path = self.DATA_DIR / "identity_state.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[IdentityCore] save failed: {e}")

    def _load(self) -> None:
        try:
            path = self.DATA_DIR / "identity_state.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self._version = data.get("version", 1)
                cs = data.get("current_state", {})
                self.current_state.values = cs.get("values", self.current_state.values)
                self.current_state.goals = cs.get("goals", self.current_state.goals)
                self.current_state.constraints = cs.get("constraints", self.current_state.constraints)
                self.current_state.traits = cs.get("traits", self.current_state.traits)
                self.current_state.obsessions = cs.get("obsessions", [])
                ts = data.get("target_state", {})
                self.target_state.values = ts.get("values", self.target_state.values)
                self.target_state.goals = ts.get("goals", self.target_state.goals)
                self.target_state.constraints = ts.get("constraints", self.target_state.constraints)
                self.target_state.traits = ts.get("traits", self.target_state.traits)
                self.evolution_path = data.get("evolution_path", [])
                self._last_evolution = data.get("last_evolution", time.time())
        except Exception as e:
            print(f"[IdentityCore] load failed: {e}")


_identity_instance: Optional[IdentityCore] = None
_identity_lock = threading.Lock()


def get_identity_core() -> IdentityCore:
    global _identity_instance
    if _identity_instance is None:
        with _identity_lock:
            if _identity_instance is None:
                _identity_instance = IdentityCore()
    return _identity_instance
