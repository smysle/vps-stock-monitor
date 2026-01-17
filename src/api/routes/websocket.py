"""
WebSocket 实时推送
"""
import logging
import asyncio
import json
from datetime import datetime
from typing import Set, Dict, Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import redis.asyncio as redis

from ..schemas import WSMessageType, WSMessage
from ..app import verify_ws_token
from ...config.settings import get_config

logger = logging.getLogger(__name__)
router = APIRouter()

# 最大连接数限制
MAX_CONNECTIONS = 100


class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self, max_connections: int = MAX_CONNECTIONS):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._max_connections = max_connections
    
    @property
    def connection_count(self) -> int:
        """当前连接数"""
        return len(self.active_connections)
    
    async def connect(self, websocket: WebSocket) -> bool:
        """
        接受新连接
        
        Returns:
            是否成功连接
        """
        async with self._lock:
            # 检查连接数限制
            if len(self.active_connections) >= self._max_connections:
                logger.warning(f"WebSocket 连接数已达上限: {self._max_connections}")
                return False
            
            await websocket.accept()
            self.active_connections.add(websocket)
        
        logger.info(f"WebSocket 连接建立，当前连接数: {len(self.active_connections)}")
        return True
    
    async def disconnect(self, websocket: WebSocket):
        """断开连接"""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket 连接断开，当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        if not self.active_connections:
            return
        
        data = json.dumps(message, default=str)
        
        disconnected = set()
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(data)
            except Exception as e:
                logger.warning(f"发送消息失败: {e}")
                disconnected.add(connection)
        
        # 清理断开的连接
        if disconnected:
            async with self._lock:
                self.active_connections -= disconnected
    
    async def send_to(self, websocket: WebSocket, message: dict):
        """发送消息到单个连接"""
        try:
            await websocket.send_text(json.dumps(message, default=str))
        except Exception as e:
            logger.warning(f"发送消息失败: {e}")


# 全局连接管理器
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """获取连接管理器"""
    return manager


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="认证 Token")
):
    """WebSocket 端点（带认证）"""
    # 验证 token
    if not await verify_ws_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        logger.warning("WebSocket 连接被拒绝：未授权")
        return
    
    # 尝试连接（检查连接数限制）
    if not await manager.connect(websocket):
        await websocket.close(code=1013, reason="Try Again Later")
        return
    
    try:
        # 发送欢迎消息
        await manager.send_to(websocket, {
            'type': WSMessageType.SYSTEM_STATUS,
            'data': {
                'message': '连接成功',
                'connected_at': datetime.now().isoformat()
            },
            'timestamp': datetime.now().isoformat()
        })
        
        # 从配置获取超时时间
        config = get_config()
        ws_timeout = config.get('api.websocket_timeout', 30.0)
        
        # 保持连接，处理消息
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=ws_timeout
                )
                
                # 限制消息大小 (64KB)
                if len(data) > 65536:
                    logger.warning("WebSocket 消息过大，已忽略")
                    continue
                
                try:
                    message = json.loads(data)
                    msg_type = message.get('type', '')
                    
                    # 处理 ping
                    if msg_type == 'ping':
                        await manager.send_to(websocket, {
                            'type': WSMessageType.PONG,
                            'data': {},
                            'timestamp': datetime.now().isoformat()
                        })
                    
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_text(json.dumps({
                        'type': WSMessageType.PING,
                        'data': {},
                        'timestamp': datetime.now().isoformat()
                    }))
                except Exception:
                    break
                    
    except WebSocketDisconnect:
        logger.info("客户端断开连接")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
    finally:
        await manager.disconnect(websocket)


async def broadcast_stock_change(product_id: str, product_name: str, status: str, price: float = None):
    """广播库存变化"""
    await manager.broadcast({
        'type': WSMessageType.STOCK_CHANGE,
        'data': {
            'product_id': product_id,
            'product_name': product_name,
            'status': status,
            'price': price,
            'changed_at': datetime.now().isoformat()
        },
        'timestamp': datetime.now().isoformat()
    })


async def broadcast_check_result(result: dict):
    """广播检查结果"""
    await manager.broadcast({
        'type': WSMessageType.CHECK_RESULT,
        'data': result,
        'timestamp': datetime.now().isoformat()
    })


async def broadcast_error(error: str, detail: str = None):
    """广播错误"""
    await manager.broadcast({
        'type': WSMessageType.ERROR,
        'data': {
            'error': error,
            'detail': detail
        },
        'timestamp': datetime.now().isoformat()
    })


class RedisSubscriber:
    """Redis 订阅器，用于接收监控事件并广播到 WebSocket"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.pubsub = None
        self._running = False
    
    async def start(self):
        """启动订阅"""
        if not self.redis:
            return
        
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(
            "vps_monitor:stock_change",
            "vps_monitor:check_result",
            "vps_monitor:error"
        )
        
        self._running = True
        logger.info("Redis 订阅已启动")
        
        # 处理消息
        while self._running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                
                if message and message['type'] == 'message':
                    channel = message['channel']
                    data = json.loads(message['data'])
                    
                    if channel == "vps_monitor:stock_change":
                        await broadcast_stock_change(**data)
                    elif channel == "vps_monitor:check_result":
                        await broadcast_check_result(data)
                    elif channel == "vps_monitor:error":
                        await broadcast_error(**data)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"处理 Redis 消息失败: {e}")
    
    async def stop(self):
        """停止订阅"""
        self._running = False
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
            logger.info("Redis 订阅已停止")
