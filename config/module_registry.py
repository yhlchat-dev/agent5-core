# -*- coding: utf-8 -*-
from config.run_mode import is_cognitive_only

COGNITIVE_ONLY_ALLOWED_MODULES = {
    "cognitive_loop",
    "planner",
    "verifier",
    "memory_core",
    "identity_core",
    "decision_engine",
    "experience_validator",
    "experience_firewall",
    "agent_private_capsule",
    "llm_bridge",
    "ui_chat_entry",
}


def should_enable_module(module_name: str) -> bool:
    if is_cognitive_only():
        return module_name in COGNITIVE_ONLY_ALLOWED_MODULES
    return True


def allow_background_tasks() -> bool:
    return not is_cognitive_only()
