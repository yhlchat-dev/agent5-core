# -*- coding: utf-8 -*-
import logging
from typing import Any, Dict, Optional

from core.runtime.global_registry import GlobalRegistry


class Wiring:

    def __init__(self, registry=None):
        self.registry = registry or GlobalRegistry.get_instance()
        self.logger = logging.getLogger("Wiring")

    def wire_controller(self, controller) -> bool:
        try:
            self.registry.register("controller", controller, metadata={"type": "executor"})
            coordinator = self.registry.get("coordinator")
            if coordinator and hasattr(controller, "coordinator"):
                controller.coordinator = coordinator
            self.logger.info("[Wiring] controller wired")
            return True
        except Exception as e:
            self.logger.error(f"[Wiring] controller wiring failed: {e}")
            return False

    def wire_agent(self, master_agent) -> bool:
        try:
            self.registry.register("master_agent", master_agent)
            controller = self.registry.get("controller")
            if controller and hasattr(master_agent, "set_controller"):
                master_agent.set_controller(controller)
            self.logger.info("[Wiring] master_agent wired")
            return True
        except Exception as e:
            self.logger.error(f"[Wiring] master_agent wiring failed: {e}")
            return False

    def wire_sub_agent(self, sub_agent) -> bool:
        try:
            task_context_manager = self.registry.get("task_context_manager")
            raw_event_store = self.registry.get("raw_event_store")
            if task_context_manager and hasattr(sub_agent, "task_context_manager"):
                sub_agent.task_context_manager = task_context_manager
            if raw_event_store and hasattr(sub_agent, "raw_event_store"):
                sub_agent.raw_event_store = raw_event_store
            self.registry.register("sub_agent", sub_agent)
            self.logger.info("[Wiring] sub_agent wired")
            return True
        except Exception as e:
            self.logger.error(f"[Wiring] sub_agent wiring failed: {e}")
            return False

    def wire_evolution(self) -> bool:
        try:
            evolution_hook = self.registry.get("evolution_hook")
            if evolution_hook:
                evolution_hook.activate()
            self.logger.info("[Wiring] evolution wired")
            return True
        except Exception as e:
            self.logger.error(f"[Wiring] evolution wiring failed: {e}")
            return False

    def wire_all(self, controller=None, master_agent=None, sub_agent=None) -> Dict[str, bool]:
        results = self._wire_all_impl(controller, master_agent, sub_agent)
        self.logger.info(f"[Wiring] all wiring: {results}")
        return results

    def _wire_all_impl(self, controller, master_agent, sub_agent) -> Dict[str, bool]:
        results = {}
        if controller:
            results["controller"] = self.wire_controller(controller)
        if master_agent:
            results["master_agent"] = self.wire_agent(master_agent)
        if sub_agent:
            results["sub_agent"] = self.wire_sub_agent(sub_agent)
        results["evolution"] = self.wire_evolution()
        unified_coordinator = self.registry.get("unified_coordinator")
        if unified_coordinator and self.registry.get("controller"):
            unified_coordinator.registry = self.registry
        return results
