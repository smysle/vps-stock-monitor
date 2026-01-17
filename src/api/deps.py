"""
依赖注入模块
"""
import logging
import threading
from typing import Optional, AsyncGenerator

import redis.asyncio as redis

from ..config.settings import ConfigManager, get_config

logger = logging.getLogger(__name__)

# Redis 连接池
_redis_pool: Optional[redis.Redis] = None
_redis_lock = threading.Lock()

# 监控器实例
_monitor = None
_monitor_lock = threading.Lock()


async def init_redis() -> Optional[redis.Redis]:
    """初始化 Redis 连接"""
    global _redis_pool
    
    config = get_config()
    redis_config = config.get('redis', {})
    
    host = redis_config.get('host', 'localhost')
    port = redis_config.get('port', 6379)
    db = redis_config.get('db', 0)
    password = redis_config.get('password') or None
    
    try:
        _redis_pool = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            encoding='utf-8',
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
        
        # 测试连接
        await _redis_pool.ping()
        logger.info(f"Redis 连接成功: {host}:{port}/{db}")
        return _redis_pool
        
    except Exception as e:
        logger.warning(f"Redis 连接失败: {e}，将使用内存存储")
        _redis_pool = None
        return None


async def close_redis():
    """关闭 Redis 连接"""
    global _redis_pool
    
    with _redis_lock:
        if _redis_pool:
            try:
                await _redis_pool.close()
                await _redis_pool.connection_pool.disconnect()
            except Exception as e:
                logger.warning(f"关闭 Redis 连接时出错: {e}")
            finally:
                _redis_pool = None
            logger.info("Redis 连接已关闭")


async def get_redis() -> Optional[redis.Redis]:
    """获取 Redis 连接（依赖注入）"""
    return _redis_pool


def get_config_dep() -> ConfigManager:
    """获取配置管理器（依赖注入）"""
    return get_config()


# 别名，修复导入问题
get_config_manager = get_config_dep


def set_monitor(monitor) -> None:
    """设置监控器实例（线程安全）"""
    global _monitor
    with _monitor_lock:
        _monitor = monitor


def get_monitor():
    """获取监控器实例（线程安全）"""
    with _monitor_lock:
        return _monitor
