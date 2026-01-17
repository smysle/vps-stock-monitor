"""
状态查询 API
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
import redis.asyncio as redis

from ..schemas import (
    ProductStatus, ProductCheckResult, MonitorStatus,
    SystemStatus, SuccessResponse
)
from ..deps import get_redis, get_config_dep, get_monitor
from ...config.settings import ConfigManager

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis Keys
MONITOR_STATUS_KEY = "vps_monitor:status"
CHECK_HISTORY_KEY = "vps_monitor:check_history"
STATS_KEY = "vps_monitor:stats"


def safe_parse_datetime(value: str) -> Optional[datetime]:
    """安全解析日期时间"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"无效的时间格式: {value}, 错误: {e}")
        return None


def safe_int(value, default: int = 0) -> int:
    """安全转换为整数"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@router.get("", response_model=SystemStatus)
async def get_system_status(
    redis_client: redis.Redis = Depends(get_redis),
    config: ConfigManager = Depends(get_config_dep)
):
    """获取系统状态"""
    monitor = get_monitor()
    
    # 基础信息
    products = config.products
    enabled_count = len([p for p in products if p.enabled])
    
    # 监控状态
    running = False
    start_time = None
    uptime_seconds = None
    total_checks = 0
    successful_checks = 0
    failed_checks = 0
    last_check_time = None
    
    if redis_client:
        status_data = await redis_client.hgetall(MONITOR_STATUS_KEY)
        if status_data:
            running = status_data.get('running', 'false').lower() == 'true'
            if status_data.get('start_time'):
                start_time = safe_parse_datetime(status_data['start_time'])
                if start_time:
                    uptime_seconds = int((datetime.now() - start_time).total_seconds())
            if status_data.get('last_check_time'):
                last_check_time = safe_parse_datetime(status_data['last_check_time'])
        
        # 统计数据
        stats_data = await redis_client.hgetall(STATS_KEY)
        if stats_data:
            total_checks = safe_int(stats_data.get('total_checks'))
            successful_checks = safe_int(stats_data.get('successful_checks'))
            failed_checks = safe_int(stats_data.get('failed_checks'))
    
    return SystemStatus(
        version="1.0.0",
        monitor=MonitorStatus(
            running=running,
            start_time=start_time,
            uptime_seconds=uptime_seconds,
            total_checks=total_checks,
            successful_checks=successful_checks,
            failed_checks=failed_checks,
            last_check_time=last_check_time
        ),
        redis_connected=redis_client is not None,
        browser_ready=monitor is not None,
        config_file=config.config_file,
        products_count=len(products),
        enabled_products_count=enabled_count
    )


@router.get("/history", response_model=List[ProductCheckResult])
async def get_check_history(
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    product_id: Optional[str] = Query(None, description="按产品ID过滤"),
    redis_client: redis.Redis = Depends(get_redis)
):
    """获取检查历史"""
    history = []
    
    if redis_client:
        # 从 Redis List 获取历史记录
        key = CHECK_HISTORY_KEY
        if product_id:
            key = f"vps_monitor:product_history:{product_id}"
        
        data = await redis_client.lrange(key, 0, limit - 1)
        
        import json
        for item in data:
            try:
                record = json.loads(item)
                history.append(ProductCheckResult(**record))
            except Exception:
                pass
    
    return history


@router.get("/stats")
async def get_stats(
    redis_client: redis.Redis = Depends(get_redis)
):
    """获取统计数据"""
    stats = {
        'total_checks': 0,
        'successful_checks': 0,
        'failed_checks': 0,
        'in_stock_notifications': 0,
        'average_check_duration_ms': 0,
        'products_by_status': {
            'in_stock': 0,
            'out_of_stock': 0,
            'unknown': 0,
            'error': 0
        },
        'last_24h_checks': 0,
        'last_24h_notifications': 0
    }
    
    if redis_client:
        # 基础统计
        stats_data = await redis_client.hgetall(STATS_KEY)
        if stats_data:
            stats['total_checks'] = safe_int(stats_data.get('total_checks'))
            stats['successful_checks'] = safe_int(stats_data.get('successful_checks'))
            stats['failed_checks'] = safe_int(stats_data.get('failed_checks'))
            stats['in_stock_notifications'] = safe_int(stats_data.get('in_stock_notifications'))
            
            total_duration = safe_int(stats_data.get('total_duration_ms'))
            if stats['total_checks'] > 0:
                stats['average_check_duration_ms'] = total_duration // stats['total_checks']
        
        # 产品状态统计
        all_products = await redis_client.hgetall("vps_monitor:products")
        for product_id in all_products.keys():
            status_key = f"vps_monitor:product_status:{product_id}"
            status = await redis_client.hget(status_key, 'status')
            if status in stats['products_by_status']:
                stats['products_by_status'][status] += 1
            else:
                stats['products_by_status']['unknown'] += 1
    
    return stats


@router.post("/reset-stats", response_model=SuccessResponse)
async def reset_stats(
    redis_client: redis.Redis = Depends(get_redis)
):
    """重置统计数据"""
    if redis_client:
        await redis_client.delete(STATS_KEY)
        await redis_client.delete(CHECK_HISTORY_KEY)
        logger.info("统计数据已重置")
    
    return SuccessResponse(message="统计数据已重置")
