"""
Telegram 通知
"""
import asyncio
import logging
import re
import warnings
import aiohttp
from aiohttp import ClientError, ClientTimeout
from typing import Optional

from .base import NotificationProvider, NotificationMessage


logger = logging.getLogger(__name__)


class TelegramNotifier(NotificationProvider):
    """Telegram 通知器"""
    
    # API URL 模板 - 不存储含 token 的 URL
    BASE_URL = "https://api.telegram.org/bot{token}/{method}"
    
    # chat_id 验证正则: 数字ID（可带负号）或 @username
    CHAT_ID_PATTERN = re.compile(r'^-?\d+$|^@[\w]{5,}$')
    
    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    REQUEST_TIMEOUT = 30
    
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        parse_mode: str = "HTML",
        disable_preview: bool = False
    ):
        """
        初始化 Telegram 通知器
        
        Args:
            bot_token: Bot Token
            chat_id: 聊天 ID (可以是用户 ID 或群组 ID)
            parse_mode: 解析模式 (HTML/Markdown/MarkdownV2)
            disable_preview: 是否禁用链接预览
        
        Raises:
            ValueError: 如果 chat_id 格式无效
        """
        # 验证 chat_id 格式
        if not self.CHAT_ID_PATTERN.match(chat_id):
            raise ValueError(f"Invalid chat_id format: {chat_id}")
        
        # 私有存储 token，不存储包含 token 的 URL
        self._bot_token = bot_token
        self.chat_id = chat_id
        self.parse_mode = parse_mode
        self.disable_preview = disable_preview
        self._session: Optional[aiohttp.ClientSession] = None
    
    def _get_api_url(self, method: str) -> str:
        """动态生成 API URL，避免存储含 token 的 URL"""
        return self.BASE_URL.format(token=self._bot_token, method=method)
    
    def __repr__(self) -> str:
        """安全的字符串表示（不暴露 token）"""
        return f"TelegramNotifier(chat_id='{self.chat_id}', bot_token='***')"
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()
    
    def __del__(self):
        """析构函数 - 检测资源泄露"""
        if hasattr(self, '_session') and self._session and not self._session.closed:
            warnings.warn(
                f"{self.__class__.__name__} was not properly closed. "
                "Use 'async with' or call 'await close()' explicitly.",
                ResourceWarning
            )
    
    @property
    def name(self) -> str:
        return "telegram"
    
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
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        retries: int = MAX_RETRIES,
        **kwargs
    ) -> Optional[dict]:
        """发起带重试的 HTTP 请求"""
        session = await self._get_session()
        last_error = None
        
        for attempt in range(retries):
            try:
                async with session.request(method, url, **kwargs) as resp:
                    # 处理速率限制
                    if resp.status == 429:
                        retry_after = int(resp.headers.get('Retry-After', 5))
                        logger.warning(f"Telegram API 限流，等待 {retry_after} 秒")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        error_text = await resp.text()
                        logger.error(f"Telegram 请求失败: {resp.status} - {error_text[:200]}")
                        return None
                        
            except (ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < retries - 1:
                    logger.warning(f"Telegram 请求失败 (尝试 {attempt + 1}/{retries}): {e}")
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue
                    
            except Exception as e:
                logger.error(f"Telegram 请求异常: {e}")
                return None
        
        if last_error:
            logger.error(f"Telegram 请求失败，已重试 {retries} 次: {last_error}")
        return None
    
    async def send(self, message: NotificationMessage) -> bool:
        """发送 Telegram 消息"""
        # 根据解析模式选择格式
        if self.parse_mode == "HTML":
            text = message.to_html()
        elif self.parse_mode in ["Markdown", "MarkdownV2"]:
            text = message.to_markdown()
        else:
            text = message.to_text()
        
        # 发送消息
        url = self._get_api_url("sendMessage")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_web_page_preview": self.disable_preview
        }
        
        data = await self._request_with_retry("POST", url, json=payload)
        if data and data.get("ok"):
            logger.info(f"Telegram 消息发送成功: {message.title}")
            return True
        else:
            logger.error(f"Telegram API 错误: {data}")
            return False
    
    async def send_photo(
        self,
        message: NotificationMessage,
        photo_url: Optional[str] = None
    ) -> bool:
        """发送带图片的消息"""
        photo = photo_url or message.image_url
        if not photo:
            return await self.send(message)
        
        url = self._get_api_url("sendPhoto")
        
        if self.parse_mode == "HTML":
            caption = message.to_html()
        else:
            caption = message.to_text()
        
        payload = {
            "chat_id": self.chat_id,
            "photo": photo,
            "caption": caption[:1024],  # Telegram 限制
            "parse_mode": self.parse_mode
        }
        
        data = await self._request_with_retry("POST", url, json=payload)
        return bool(data and data.get("ok"))
    
    async def test(self) -> bool:
        """测试 Telegram 连接"""
        url = self._get_api_url("getMe")
        data = await self._request_with_retry("GET", url)
        
        if data and data.get("ok"):
            bot_info = data.get("result", {})
            logger.info(f"Telegram Bot 连接成功: @{bot_info.get('username')}")
            return True
        return False
