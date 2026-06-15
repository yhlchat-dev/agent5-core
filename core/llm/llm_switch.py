# -*- coding: utf-8 -*-
import logging


class LLMSwitch:

    # [枚举值] - 无需迁移
    MODES = ("safe", "balanced", "full")

    def __init__(self, mode: str = 'safe') -> None:
        self.mode = mode
        self.logger = logging.getLogger("LLMSwitch")

    def is_safe_mode(self) -> bool:
        return self.mode == "safe"

    def is_balanced_mode(self) -> bool:
        return self.mode == "balanced"

    def is_full_mode(self) -> bool:
        return self.mode == "full"

    def enable_safe(self) -> None:
        self._enable_safe_impl()
        self.logger.info("[LLMSwitch] mode → safe")

    def _enable_safe_impl(self) -> None:
        self.mode = "safe"

    def enable_balanced(self) -> None:
        self._enable_balanced_impl()
        self.logger.info("[LLMSwitch] mode → balanced")

    def _enable_balanced_impl(self) -> None:
        self.mode = "balanced"

    def enable_full(self) -> None:
        self._enable_full_impl()
        self.logger.info("[LLMSwitch] mode → full")

    def _enable_full_impl(self) -> None:
        self.mode = "full"

    def set_mode(self, mode: str) -> None:
        self._set_mode_impl(mode)
        self.logger.info(f"[LLMSwitch] mode → {mode}")

    def _set_mode_impl(self, mode: str) -> None:
        if mode not in self.MODES:
            raise ValueError(f"Invalid mode: {mode}, must be one of {self.MODES}")
        self.mode = mode

    def get_mode(self) -> str:
        return self.mode
