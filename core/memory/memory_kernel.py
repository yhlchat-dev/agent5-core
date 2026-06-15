# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Optional
"""
Memory Kernel — 统一记忆控制核心

管理4层记忆的读写、检索和生命周期。
所有记忆操作必须通过此入口。

架构：
  MemoryKernel
    ├── WorkingMemory   (工作记忆：raw_trace, 即时上下文)
    ├── EpisodicMemory  (情景记忆：短期经验, 事件序列)
    ├── SemanticMemory  (语义记忆：模式, 知识, 策略)
    └── SelfMemory      (自我记忆：身份, 价值观, 核心偏好)
"""
import logging
import time
from typing import Dict, Any, Optional, List

from core.memory.memory_router import MemoryRouter


class MemoryKernel:
    """
    统一记忆控制核心。

    职责：
    1. write(): 路由写入对应层
    2. read(): 跨层检索
    3. lifecycle 管理
    4. decay 衰减
    """

    def __init__(self, router: Optional[Any] = None) -> None:
        self.router = router or MemoryRouter()
        self.layers = {}
        self.logger = logging.getLogger("MemoryKernel")
        self._write_count = 0
        self._read_count = 0

        self._init_layers()

    def _init_layers(self) -> None:
        try:
            from core.memory.layers.working_memory import WorkingMemory
            self.layers["working"] = WorkingMemory()
        except Exception:
            self.layers["working"] = _FallbackLayer("working")

        try:
            from core.memory.layers.episodic_memory import EpisodicMemory
            self.layers["episodic"] = EpisodicMemory()
        except Exception:
            self.layers["episodic"] = _FallbackLayer("episodic")

        try:
            from core.memory.layers.semantic_memory import SemanticMemory
            self.layers["semantic"] = SemanticMemory()
        except Exception:
            self.layers["semantic"] = _FallbackLayer("semantic")

        try:
            from core.memory.layers.self_memory import SelfMemory
            self.layers["self"] = SelfMemory()
        except Exception:
            self.layers["self"] = _FallbackLayer("self")

    def write(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        写入记忆：路由到对应层存储。

        Args:
            data: 记忆数据 dict，需包含 type 字段

        Returns:
            {"layer": str, "id": str, "stored": bool}
        """
        self._write_count += 1

        if not isinstance(data, dict):
            data = {"type": "raw_trace", "data": data}

        layer_name = self.router.route(data)
        layer = self.layers.get(layer_name)

        if layer is None:
            self.logger.warning("未找到记忆层: '{}'".format(layer_name))
            return {"layer": layer_name, "id": None, "stored": False}

        result = self._write_impl(data, layer_name, layer)
        self.logger.debug(
            "写入记忆: layer={}, type={}".format(
                layer_name, data.get("type", "unknown")
            )
        )

        return result

    def _write_impl(self, data: Dict[str, Any], layer_name: str, layer) -> Dict[str, Any]:
        data.setdefault("timestamp", time.time())
        data.setdefault("_target_layer", layer_name)

        layer.store(data)

        return {
            "layer": layer_name,
            "id": data.get("id", str(id(data))),
            "stored": True,
        }

    def read(self, query: str) -> List[Dict[str, Any]]:
        """
        跨层检索记忆。

        优先级：self > semantic > episodic > working
        """
        self._read_count += 1

        results = []
        for layer_name in ["self", "semantic", "episodic", "working"]:
            layer_results = self._search_layer(layer_name, query)
            for item in layer_results:
                if isinstance(item, dict):
                    item["_source_layer"] = layer_name
            results.extend(layer_results)

        return results

    def _search_layer(self, layer_name: str, query: str) -> List[Dict[str, Any]]:
        layer = self.layers.get(layer_name)
        if layer is None:
            return []
        try:
            return layer.search(query)
        except Exception as e:
            self.logger.debug("层 '{}' 检索失败: {}".format(layer_name, e))
            return []

    def read_layer(self, layer_name: str, query: str = None) -> List[Dict[str, Any]]:
        """
        从指定层检索记忆。
        """
        layer = self.layers.get(layer_name)
        if layer is None:
            return []
        if query is None:
            return layer.get_all() if hasattr(layer, 'get_all') else []
        return layer.search(query)

    def promote(self, memory_id: str, from_layer: str, to_layer: str) -> bool:
        """
        将记忆从低层提升到高层（如 episodic → semantic）。
        """
        src = self.layers.get(from_layer)
        dst = self.layers.get(to_layer)

        if src is None or dst is None:
            return False

        try:
            item = src.get(memory_id) if hasattr(src, 'get') else None
            if item is None:
                return False

            if isinstance(item, dict):
                item["promoted_from"] = from_layer
                item["promoted_at"] = time.time()

            dst.store(item)
            if hasattr(src, 'remove'):
                src.remove(memory_id)

            self.logger.info(
                "记忆提升: {} → {}, id={}".format(from_layer, to_layer, memory_id)
            )
            return True
        except Exception as e:
            self.logger.warning("记忆提升失败: {}".format(e))
            return False

    def decay_all(self) -> None:
        """
        对所有层执行衰减。
        """
        for layer_name, layer in self.layers.items():
            if hasattr(layer, 'decay'):
                try:
                    layer.decay()
                except Exception as e:
                    self.logger.debug("层 '{}' 衰减失败: {}".format(layer_name, e))

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "write_count": self._write_count,
            "read_count": self._read_count,
            "layers": {},
        }
        for name, layer in self.layers.items():
            layer_type = type(layer).__name__
            count = len(layer._store) if hasattr(layer, '_store') else 0
            stats["layers"][name] = {
                "type": layer_type,
                "count": count,
            }
        stats["router"] = self.router.get_stats()
        return stats


class _FallbackLayer:
    """
    降级记忆层：当正式层无法加载时使用。
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._store = []

    def store(self, data: Dict[str, Any]) -> bool:
        self._store.append(data)
        return True

    def search(self, query: str) -> List[Any]:
        return list(self._store)

    def get_all(self) -> List[Any]:
        return list(self._store)

    def decay(self) -> None:
        pass
