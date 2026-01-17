"""
Redis 服务模块
负责与 Redis 交互，存储监控状态和事件发布
"""
import json
import logging
import functools
from datetime import datetime
from typing import Optional, Dict, Any, TypeVar, Callable

import redis.asyncio as redis
from redis.exceptions import RedisError

from ..config.settings import get_config

logger = logging.getLogger(__name__)

T = TypeVar('T')


def redis_safe(default: T = None) -> Callable:
    """Redis 操作安全装饰器，捕获异常并返回默认值"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs) -> T:
            if not self.client:
                return default
            try:
                return await func(self, *args, **kwargs)
            except RedisError as e:
                logger.error(f"Redis 操作失败 [{func.__name__}]: {e}")
                return default
            except Exception as e:
                logger.error(f"Redis 操作异常 [{func.__name__}]: {e}")
                return default
        return wrapper
    return decorator


class RedisService:
    """Redis 服务"""
    
    # Key 前缀
    PREFIX = "vps_monitor"
    
    # Keys
    PRODUCTS_KEY = f"{PREFIX}:products"
    MONITOR_STATUS_KEY = f"{PREFIX}:status"
    STATS_KEY = f"{PREFIX}:stats"
    CHECK_HISTORY_KEY = f"{PREFIX}:check_history"
    
    # 单例
    _instance: Optional['RedisService'] = None
    
    def __init__(self, client: redis.Redis):
        self.client = client
    
    @classmethod
    async def create(cls) -> Optional['RedisService']:
        """从配置创建 Redis 服务（单例）"""
        if cls._instance is not None:
            return cls._instance
        
        config = get_config()
        redis_config = config.get('redis', {})
        
        host = redis_config.get('host', 'localhost')
        port = redis_config.get('port', 6379)
        db = redis_config.get('db', 0)
        password = redis_config.get('password') or None
        
        try:
            client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                encoding='utf-8',
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            
            await client.ping()
            logger.info(f"Redis 连接成功: {host}:{port}/{db}")
            
            cls._instance = cls(client)
            return cls._instance
        except Exception as e:
            logger.warning(f"Redis 连接失败: {e}")
            return None
    
    async def close(self):
        """关闭连接"""
        if self.client:
            try:
                await self.client.close()
                await self.client.connection_pool.disconnect()
            except Exception as e:
                logger.warning(f"关闭 Redis 连接时出错: {e}")
            finally:
                self.client = None
                RedisService._instance = None
    
    async def is_healthy(self) -> bool:
        """健康检查"""
        if not self.client:
            return False
        try:
            await self.client.ping()
            return True
        except Exception:
            return False
    
    # ==================== 监控状态 ====================
    
    @redis_safe(default=None)
    async def set_monitor_running(self, running: bool):
        """设置监控运行状态"""
        data = {
            'running': '1' if running else '0',
            'updated_at': datetime.now().isoformat()
        }
        if running:
            data['start_time'] = datetime.now().isoformat()
        
        await self.client.hset(self.MONITOR_STATUS_KEY, mapping=data)
    
    @redis_safe(default=None)
    async def set_last_check_time(self):
        """更新最后检查时间"""
        await self.client.hset(
            self.MONITOR_STATUS_KEY,
            'last_check_time',
            datetime.now().isoformat()
        )
    
    @redis_safe(default={})
    async def get_monitor_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        return await self.client.hgetall(self.MONITOR_STATUS_KEY)
    
    # ==================== 产品状态 ====================
    
    @redis_safe(default=None)
    async def update_product_status(
        self,
        product_id: str,
        status: str,
        price: Optional[float] = None,
        stock_text: Optional[str] = None
    ):
        """更新产品状态（原子操作）"""
        # 验证 product_id 不包含特殊字符
        if ':' in product_id or not product_id:
            logger.warning(f"无效的 product_id: {product_id}")
            return
        
        key = f"{self.PREFIX}:product_status:{product_id}"
        
        # 使用 Pipeline 保证原子性
        async with self.client.pipeline(transaction=True) as pipe:
            pipe.hincrby(key, 'check_count', 1)
            
            data = {
                'status': status,
                'last_checked': datetime.now().isoformat()
            }
            
            if price is not None:
                data['price'] = str(price)
            if stock_text:
                data['stock_text'] = stock_text
            
            if status == 'in_stock':
                data['last_in_stock'] = datetime.now().isoformat()
            
            pipe.hset(key, mapping=data)
            # 设置过期时间（30天）
            pipe.expire(key, 30 * 24 * 3600)
            
            await pipe.execute()
    
    @redis_safe(default={})
    async def get_product_status(self, product_id: str) -> Dict[str, Any]:
        """获取产品状态"""
        key = f"{self.PREFIX}:product_status:{product_id}"
        return await self.client.hgetall(key)
    
    # ==================== 统计 ====================
    
    @redis_safe(default=None)
    async def increment_stats(
        self,
        success: bool = True,
        duration_ms: int = 0,
        in_stock: bool = False
    ):
        """增加统计计数（原子操作）"""
        async with self.client.pipeline(transaction=True) as pipe:
            pipe.hincrby(self.STATS_KEY, 'total_checks', 1)
            
            if success:
                pipe.hincrby(self.STATS_KEY, 'successful_checks', 1)
            else:
                pipe.hincrby(self.STATS_KEY, 'failed_checks', 1)
            
            if in_stock:
                pipe.hincrby(self.STATS_KEY, 'in_stock_notifications', 1)
            
            pipe.hincrby(self.STATS_KEY, 'total_duration_ms', duration_ms)
            
            await pipe.execute()
    
    @redis_safe(default={})
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计数据"""
        return await self.client.hgetall(self.STATS_KEY)
    
    @redis_safe(default=None)
    async def reset_stats(self):
        """重置统计"""
        await self.client.delete(self.STATS_KEY)
    
    # ==================== 历史记录 ====================
    
    @redis_safe(default=None)
    async def add_check_history(
        self,
        product_id: str,
        product_name: str,
        status: str,
        price: Optional[float] = None,
        duration_ms: int = 0,
        changed: bool = False
    ):
        """添加检查历史"""
        # 从配置获取历史记录限制
        config = get_config()
        max_global_history = config.get('data.max_global_history', 1000)
        max_product_history = config.get('data.max_product_history', 100)
        
        record = {
            'product_id': product_id,
            'product_name': product_name,
            'status': status,
            'price': price,
            'checked_at': datetime.now().isoformat(),
            'duration_ms': duration_ms,
            'changed': changed
        }
        
        async with self.client.pipeline(transaction=True) as pipe:
            # 添加到全局历史
            pipe.lpush(self.CHECK_HISTORY_KEY, json.dumps(record))
            pipe.ltrim(self.CHECK_HISTORY_KEY, 0, max_global_history - 1)
            
            # 添加到产品历史
            if ':' not in product_id and product_id:
                product_history_key = f"{self.PREFIX}:product_history:{product_id}"
                pipe.lpush(product_history_key, json.dumps(record))
                pipe.ltrim(product_history_key, 0, max_product_history - 1)
                # 产品历史设置过期时间（7天）
                pipe.expire(product_history_key, 7 * 24 * 3600)
            
            await pipe.execute()
    
    @redis_safe(default=[])
    async def get_check_history(self, limit: int = 50) -> list:
        """获取检查历史"""
        data = await self.client.lrange(self.CHECK_HISTORY_KEY, 0, limit - 1)
        results = []
        for item in data:
            try:
                results.append(json.loads(item))
            except json.JSONDecodeError:
                logger.warning(f"跳过损坏的历史记录")
        return results
    
    # ==================== 事件发布 ====================
    
    @redis_safe(default=None)
    async def publish_stock_change(
        self,
        product_id: str,
        product_name: str,
        status: str,
        price: Optional[float] = None
    ):
        """发布库存变化事件"""
        await self.client.publish(
            f"{self.PREFIX}:stock_change",
            json.dumps({
                'product_id': product_id,
                'product_name': product_name,
                'status': status,
                'price': price
            })
        )
    
    @redis_safe(default=None)
    async def publish_check_result(self, result: dict):
        """发布检查结果事件"""
        await self.client.publish(
            f"{self.PREFIX}:check_result",
            json.dumps(result, default=str)
        )
    
    @redis_safe(default=None)
    async def publish_command(self, command: str):
        """发布命令"""
        await self.client.publish(f"{self.PREFIX}:command", command)
