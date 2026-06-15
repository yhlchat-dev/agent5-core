# -*- coding: utf-8 -*-
import logging
import threading
from typing import Any, Callable, Dict, List, Optional


class GlobalRegistry:

    _instance = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._modules: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._metadata: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger("GlobalRegistry")

    @classmethod
    def get_instance(cls) -> 'GlobalRegistry':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def register(self, name: str, module: Any, metadata: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._modules[name] = module
            if metadata:
                self._metadata[name] = metadata
            self.logger.info(f"[GlobalRegistry] registered: {name}")

    def register_factory(self, name: str, factory: Callable[..., Any], metadata: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._factories[name] = factory
            if metadata:
                self._metadata[name] = metadata

    def get(self, name: str, default: Optional[Any] = None) -> Any:
        with self._lock:
            if name in self._modules:
                return self._modules[name]
            if name in self._factories:
                module = self._factories[name]()
                self._modules[name] = module
                del self._factories[name]
                return module
            return default

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._modules or name in self._factories

    def unregister(self, name: str) -> bool:
        with self._lock:
            removed = False
            if name in self._modules:
                del self._modules[name]
                removed = True
            if name in self._factories:
                del self._factories[name]
                removed = True
            self._metadata.pop(name, None)
            return removed

    def list_modules(self) -> List[str]:
        with self._lock:
            names = set(self._modules.keys()) | set(self._factories.keys())
            return sorted(names)

    def get_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        return self._metadata.get(name)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "modules": list(self._modules.keys()),
                "factories": list(self._factories.keys()),
                "total": len(self._modules) + len(self._factories),
            }
