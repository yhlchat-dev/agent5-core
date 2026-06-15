"""
安全模块
"""
from typing import List, Dict, Any, Optional
import yaml
from pathlib import Path


class SafetyManager:
    """
    安全管理器
    管理黑名单和急停功能
    """
    
    def __init__(self, config_path: str = "core/safety/forbidden_areas.yaml"):
        self.config_path = config_path
        self._forbidden_areas: List[str] = []
        self._emergency_stop = False
        self._load_config()
    
    def _load_config(self) -> None:
        """加载配置"""
        try:
            path = Path(self.config_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return self._load_config_io(f)
        except Exception:
            self._forbidden_areas = [
                "系统设置",
                "注册表编辑器",
                "任务管理器",
                "控制面板",
            ]

    def _load_config_io(self, f) -> None:
        config = yaml.safe_load(f)
        self._forbidden_areas = config.get("forbidden_areas", [])
    
    def is_forbidden(self, target: str) -> bool:
        """检查是否在黑名单中"""
        target_lower = target.lower()
        
        for area in self._forbidden_areas:
            if area.lower() in target_lower:
                return True
        
        return False
    
    def add_forbidden_area(self, area: str) -> None:
        """添加禁止区域"""
        if area not in self._forbidden_areas:
            self._forbidden_areas.append(area)
    
    def remove_forbidden_area(self, area: str) -> bool:
        """移除禁止区域"""
        if area in self._forbidden_areas:
            self._forbidden_areas.remove(area)
            return True
        return False
    
    def trigger_emergency_stop(self) -> None:
        """触发急停"""
        self._emergency_stop = True
    
    def reset_emergency_stop(self) -> None:
        """重置急停"""
        self._emergency_stop = False
    
    def is_emergency_stopped(self) -> bool:
        """检查是否急停"""
        return self._emergency_stop
    
    def validate_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """校验动作安全性"""
        result = {
            "safe": True,
            "reason": "",
        }
        
        if self._emergency_stop:
            result["safe"] = False
            result["reason"] = "急停已触发"
            return result
        
        action_str = str(action).lower()
        
        for area in self._forbidden_areas:
            if area.lower() in action_str:
                result["safe"] = False
                result["reason"] = f"涉及禁止区域: {area}"
                return result
        
        return result
    
    def get_forbidden_areas(self) -> List[str]:
        """获取禁止区域列表"""
        return self._forbidden_areas.copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "forbidden_areas_count": len(self._forbidden_areas),
            "emergency_stop": self._emergency_stop,
        }
