"""
验证码处理模块
"""
from .capmonster import CapMonsterClient, TaskResult
from .solver import CaptchaSolver

__all__ = ["CapMonsterClient", "TaskResult", "CaptchaSolver"]
