"""
FastAPI 管理接口模块
"""

from .app import create_app, get_app
from .deps import get_redis, get_config_dep, get_monitor, set_monitor

__all__ = ['create_app', 'get_app', 'get_redis', 'get_config_dep', 'get_monitor', 'set_monitor']
