"""
Discord 通知
"""
import asyncio
import logging
import re
import aiohttp
from aiohttp import ClientError, ClientTimeout
from typing import Optional, List, Dict, Any
from datetime import datetime

from .base import NotificationProvider, NotificationMessage, NotificationLevel


logger = logging.getLogger(__name__)


class DiscordNotifier(NotificationProvider):
    """Discord Webhook 通知器"""
    
    # 通知级别对应的颜色
    LEVEL_COLORS = {
        NotificationLevel.INFO: 0x3498db,      # 蓝色
        NotificationLevel.SUCCESS: 0x2ecc71,   # 绿色
        NotificationLevel.WARNING: 0xf39c12,   # 橙色
        NotificationLevel.ERROR: 0xe74c3c,     # 红色
    }
    
    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    REQUEST_TIMEOUT = 30
    
    # 有效 ID 正则
    VALID_ID_PATTERN = re.compile(r'^\d{17,20}$')
    
    def __init__(
        self,
        webhook_url: str,
        username: Optional[str] = "VPS Monitor",
        avatar_url: Optional[str] = None,
        mention_roles: Optional[List[str]] = None,
        mention_users: Optional[List[str]] = None
    ):
        """
        初始化 Discord 通知器
        
        Args:
            webhook_url: Discord Webhook URL
            username: Bot 显示名称
            avatar_url: Bot 头像 URL
            mention_roles: 要 @ 的角色 ID 列表
            mention_users: 要 @ 的用户 ID 列表
        """
        self._webhook_url = webhook_url  # 私有属性，不暴露
        self.username = username
        self.avatar_url = avatar_url
        # 验证并过滤 ID
        self.mention_roles = [r for r in (mention_roles or []) if self._validate_id(r)]
        self.mention_users = [u for u in (mention_users or []) if self._validate_id(u)]
        self._session: Optional[aiohttp.ClientSession] = None
    
    def __repr__(self) -> str:
        """安全的字符串表示（不暴露 webhook URL）"""
        return f"DiscordNotifier(username={self.username})"
    
    @property
    def name(self) -> str:
        return "discord"
    
    def _validate_id(self, id_str: str) -> bool:
        """验证 Discord ID 格式"""
        return bool(self.VALID_ID_PATTERN.match(str(id_str)))
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.REQUEST_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def _build_embed(self, message: NotificationMessage) -> Dict[str, Any]:
        """构建 Discord Embed"""
        embed = {
            "title": message.title[:256],  # Discord 限制
            "description": message.body[:4096],  # Discord 限制
            "color": self.LEVEL_COLORS.get(message.level, 0x3498db),
            "timestamp": message.timestamp.isoformat(),
        }
        
        if message.url:
            embed["url"] = message.url
        
        if message.image_url:
            embed["thumbnail"] = {"url": message.image_url}
        
        if message.tags:
            embed["footer"] = {"text": " | ".join(message.tags)[:2048]}
        
        return embed
    
    def _build_mentions(self) -> str:
        """构建 @ 提及"""
        mentions = []
        for role_id in self.mention_roles:
            mentions.append(f"<@&{role_id}>")
        for user_id in self.mention_users:
            mentions.append(f"<@{user_id}>")
        return " ".join(mentions)
    
    async def _request_with_retry(
        self,
        payload: Dict[str, Any],
        retries: int = MAX_RETRIES
    ) -> bool:
        """发起带重试的 HTTP 请求"""
        session = await self._get_session()
        last_error = None
        
        for attempt in range(retries):
            try:
                async with session.post(self._webhook_url, json=payload) as resp:
                    # 处理速率限制
                    if resp.status == 429:
                        retry_after = float(resp.headers.get('Retry-After', 5))
                        logger.warning(f"Discord API 限流，等待 {retry_after} 秒")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    if resp.status in [200, 204]:
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"Discord 请求失败: {resp.status} - {error_text[:200]}")
                        return False
                        
            except (ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < retries - 1:
                    logger.warning(f"Discord 请求失败 (尝试 {attempt + 1}/{retries}): {e}")
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue
                    
            except Exception as e:
                logger.error(f"Discord 请求异常: {e}")
                return False
        
        if last_error:
            logger.error(f"Discord 请求失败，已重试 {retries} 次: {last_error}")
        return False
    
    async def send(self, message: NotificationMessage) -> bool:
        """发送 Discord 消息"""
        payload: Dict[str, Any] = {
            "embeds": [self._build_embed(message)]
        }
        
        if self.username:
            payload["username"] = self.username
        
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        
        # 添加 @ 提及
        mentions = self._build_mentions()
        if mentions:
            payload["content"] = mentions
        
        if await self._request_with_retry(payload):
            logger.info(f"Discord 消息发送成功: {message.title}")
            return True
        return False
    
    async def test(self) -> bool:
        """测试 Discord Webhook"""
        test_message = NotificationMessage(
            title="🔔 测试通知",
            body="VPS 库存监控系统连接测试成功！",
            level=NotificationLevel.INFO
        )
        return await self.send(test_message)
