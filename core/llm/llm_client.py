# -*- coding: utf-8 -*-
import logging
from core.llm.llm_switch import LLMSwitch
from core.llm.data_filter import DataFilter
from core.llm.context_builder import ContextBuilder
from core.safety.output_sanitizer import OutputSanitizer


from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class LLMClientInitContext:
    switch: Optional[Any] = None
    data_filter: Optional[Dict[str, Any]] = None
    builder: Optional[Any] = None
    sanitizer: Optional[Any] = None
    llm_service: Optional[Any] = None


class LLMClient:

    def __init__(self, switch: Optional[Any] = None, data_filter: Dict[str, Any] = None, builder: Optional[Any] = None, sanitizer: Optional[Any] = None, llm_service: Optional[Any] = None) -> None:
        ctx = LLMClientInitContext(switch=switch, data_filter=data_filter, builder=builder, sanitizer=sanitizer, llm_service=llm_service)
        self._init_with_context(ctx)

    def _init_with_context(self, ctx: LLMClientInitContext) -> None:
        self.switch = ctx.switch or LLMSwitch()
        self.data_filter = ctx.data_filter or DataFilter()
        self.builder = ctx.builder or ContextBuilder()
        self.sanitizer = ctx.sanitizer or OutputSanitizer()
        self.llm_service = ctx.llm_service
        self.logger = logging.getLogger("LLMClient")

    def call(self, task: Any, result: Dict[str, Any], memory: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        filtered_context = self._call_impl(task, result, memory)
        self.logger.info(
            f"[LLMClient] call mode={self.switch.get_mode()} "
            f"fields={list(filtered_context.keys())}"
        )
        return self._call_llm(filtered_context)

    def _call_impl(self, task, result, memory):
        context = self.builder.build(task, result, memory)

        filtered_context = self.data_filter.filter(
            context,
            mode=self.switch.get_mode(),
        )

        if self.switch.is_safe_mode() or self.switch.is_balanced_mode():
            filtered_context = self.sanitizer.sanitize_dict(filtered_context)

        return filtered_context

    def _call_llm(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self.llm_service:
            prompt = self._context_to_prompt(context)
            return self.llm_service.generate(prompt)

        return {"status": "done", "context_keys": list(context.keys())}

    def _context_to_prompt(self, context: Dict[str, Any]) -> str:
        parts = []
        for key, value in context.items():
            if value is not None:
                parts.append(f"{key}: {value}")
        return "\n".join(parts)

    def set_mode(self, mode: str) -> None:
        self.switch.set_mode(mode)

    def get_mode(self) -> str:
        return self.switch.get_mode()
