from enum import Enum


class ApprovalMode(Enum):
    """
    工具执行批准模式
    
    定义了在执行工具/技能前是否需要用户同意的策略
    """
    
    SPECIFIED = "specified"
    """由 MCP 的方法自己指定，或由 skills 中的 SKILL.md 说明指定"""
    
    ALWAYS = "always"
    """所有调用都需要用户同意"""
    
    AUTO = "auto"
    """所有调用都自动执行"""
    
    def __str__(self):
        return self.value
    
    @classmethod
    def from_string(cls, value: str):
        """从字符串转换为 enum"""
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Invalid ApprovalMode: {value}. Must be one of {[m.value for m in cls]}")
