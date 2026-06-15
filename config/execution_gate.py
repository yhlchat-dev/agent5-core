# -*- coding: utf-8 -*-
from config.run_mode import is_cognitive_only

COGNITIVE_ONLY_ALLOWED_COMPONENTS = {
    "cognitive_loop",
    "planner",
    "verifier",
    "executor",
    "memory_core",
    "identity_core",
    "decision_engine",
    "experience_validator",
    "experience_firewall",
    "agent_private_capsule",
    "llm_bridge",
}


def allow_execution(component: str) -> bool:
    if is_cognitive_only():
        return component in COGNITIVE_ONLY_ALLOWED_COMPONENTS
    return True


class DisabledInCognitiveMode(Exception):
    pass
