"""
系统管理 API
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import redis.asyncio as redis

from ..schemas import SuccessResponse
from ..deps import get_redis, get_config_dep, get_monitor
from ...config.settings import ConfigManager

logger = logging.getLogger(__name__)
router = APIRouter()

MONITOR_STATUS_KEY = "vps_monitor:status"


@router.post("/start", response_model=SuccessResponse)
async def start_monitor(
    redis_client: redis.Redis = Depends(get_redis)
):
    """启动监控"""
    monitor = get_monitor()
    
    if not monitor:
        raise HTTPException(status_code=503, detail="监控器未初始化")
    
    if redis_client:
        from datetime import datetime
        await redis_client.hset(MONITOR_STATUS_KEY, mapping={
            'running': 'true',
            'start_time': datetime.now().isoformat()
        })
    
    # 发布启动命令
    if redis_client:
        await redis_client.publish("vps_monitor:command", "start")
    
    logger.info("监控已启动")
    return SuccessResponse(message="监控已启动")


@router.post("/stop", response_model=SuccessResponse)
async def stop_monitor(
    redis_client: redis.Redis = Depends(get_redis)
):
    """停止监控"""
    if redis_client:
        await redis_client.hset(MONITOR_STATUS_KEY, 'running', 'false')
        await redis_client.publish("vps_monitor:command", "stop")
    
    logger.info("监控已停止")
    return SuccessResponse(message="监控已停止")


@router.post("/reload-config", response_model=SuccessResponse)
async def reload_config(
    config: ConfigManager = Depends(get_config_dep)
):
    """重新加载配置"""
    success = config.reload()
    
    if success:
        logger.info("配置已重新加载")
        return SuccessResponse(message="配置已重新加载")
    else:
        raise HTTPException(status_code=500, detail="配置加载失败")


@router.get("/config")
async def get_current_config(
    config: ConfigManager = Depends(get_config_dep)
):
    """获取当前配置（脱敏）"""
    return {
        'monitor': {
            'check_interval': config.monitor.check_interval,
            'retry_interval': config.monitor.retry_interval,
            'max_retries': config.monitor.max_retries,
            'concurrent_checks': config.monitor.concurrent_checks
        },
        'browser': {
            'headless': config.browser.headless,
            'timeout': config.browser.timeout
        },
        'proxy': {
            'enabled': config.proxy.enabled
        },
        'notifications': {
            'telegram': {
                'enabled': config.notifications.telegram.enabled
            },
            'discord': {
                'enabled': config.notifications.discord.enabled
            },
            'email': {
                'enabled': config.notifications.email.enabled
            }
        },
        'products_count': len(config.products),
        'affiliates': list(config.affiliates.keys())
    }


@router.post("/check-all", response_model=SuccessResponse)
async def trigger_check_all(
    redis_client: redis.Redis = Depends(get_redis)
):
    """触发全部产品检查"""
    if redis_client:
        await redis_client.publish("vps_monitor:command", "check_all")
    
    logger.info("已触发全部产品检查")
    return SuccessResponse(message="已触发全部产品检查")


@router.post("/clear-cache", response_model=SuccessResponse)
async def clear_cache(
    redis_client: redis.Redis = Depends(get_redis)
):
    """清除缓存"""
    if redis_client:
        # 清除状态缓存
        keys = await redis_client.keys("vps_monitor:product_status:*")
        if keys:
            await redis_client.delete(*keys)
        
        logger.info(f"已清除 {len(keys)} 个状态缓存")
    
    monitor = get_monitor()
    if monitor:
        monitor.clear_cache()
    
    return SuccessResponse(message="缓存已清除")


@router.get("/health")
async def health_check(
    redis_client: redis.Redis = Depends(get_redis)
):
    """健康检查（用于 Docker/K8s）"""
    redis_ok = False
    
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            pass
    
    return {
        'status': 'healthy' if redis_ok else 'degraded',
        'redis': redis_ok,
        'version': '1.0.0'
    }


@router.get("/validate-config")
async def validate_config(
    config: ConfigManager = Depends(get_config_dep)
):
    """验证配置"""
    errors = config.validate()
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }
