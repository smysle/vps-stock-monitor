"""
通知基类
"""
import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum
from urllib.parse import urlparse


class NotificationLevel(Enum):
    """通知级别"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


def _escape_html(text: str) -> str:
    """HTML 转义"""
    return html.escape(text) if text else ""


def _escape_markdown(text: str) -> str:
    """Markdown 转义特殊字符"""
    if not text:
        return ""
    # 转义 Markdown 特殊字符
    special_chars = r'\_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def _validate_url(url: str) -> bool:
    """验证 URL 是否安全"""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        # 只允许 http 和 https 协议
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


@dataclass
class NotificationMessage:
    """通知消息"""
    title: str
    body: str
    level: NotificationLevel = NotificationLevel.INFO
    url: Optional[str] = None
    image_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_text(self) -> str:
        """转换为纯文本"""
        lines = [f"【{self.title}】", "", self.body]
        if self.url and _validate_url(self.url):
            lines.extend(["", f"链接: {self.url}"])
        if self.tags:
            # 过滤掉可能的恶意标签
            safe_tags = [t for t in self.tags if t and len(t) < 50]
            lines.extend(["", f"标签: {', '.join(safe_tags)}"])
        return "\n".join(lines)
    
    def to_html(self) -> str:
        """转换为 HTML（安全转义）"""
        safe_title = _escape_html(self.title)
        safe_body = _escape_html(self.body)
        
        html_content = f"<b>{safe_title}</b>\n\n{safe_body}"
        
        if self.url and _validate_url(self.url):
            safe_url = _escape_html(self.url)
            html_content += f'\n\n<a href="{safe_url}">查看详情</a>'
        
        if self.tags:
            safe_tags = [_escape_html(t) for t in self.tags if t and len(t) < 50]
            html_content += f"\n\n标签: {', '.join(safe_tags)}"
        
        return html_content
    
    def to_markdown(self) -> str:
        """转换为 Markdown（安全转义）"""
        safe_title = _escape_markdown(self.title)
        safe_body = _escape_markdown(self.body)
        
        md = f"**{safe_title}**\n\n{safe_body}"
        
        if self.url and _validate_url(self.url):
            # URL 不需要完全转义，但需要验证
            md += f"\n\n[查看详情]({self.url})"
        
        if self.tags:
            safe_tags = [_escape_markdown(t) for t in self.tags if t and len(t) < 50]
            md += f"\n\n标签: {', '.join(safe_tags)}"
        
        return md


class NotificationProvider(ABC):
    """通知提供者基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        pass
    
    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool:
        """
        发送通知
        
        Args:
            message: 通知消息
            
        Returns:
            是否发送成功
        """
        pass
    
    @abstractmethod
    async def test(self) -> bool:
        """
        测试连接
        
        Returns:
            是否连接成功
        """
        pass


class NotificationManager:
    """通知管理器"""
    
    def __init__(self):
        self.providers: List[NotificationProvider] = []
    
    def add_provider(self, provider: NotificationProvider):
        """添加通知提供者"""
        self.providers.append(provider)
    
    def remove_provider(self, name: str):
        """移除通知提供者"""
        self.providers = [p for p in self.providers if p.name != name]
    
    async def send_all(self, message: NotificationMessage) -> dict:
        """
        向所有提供者并发发送通知
        
        Returns:
            {provider_name: success}
        """
        import asyncio
        
        if not self.providers:
            return {}
        
        async def send_to_provider(provider: NotificationProvider) -> tuple:
            try:
                result = await provider.send(message)
                return (provider.name, result)
            except Exception:
                return (provider.name, False)
        
        # 并发发送到所有提供者
        tasks = [send_to_provider(p) for p in self.providers]
        results_list = await asyncio.gather(*tasks)
        
        return dict(results_list)
    
    async def test_all(self) -> dict:
        """
        并发测试所有提供者
        
        Returns:
            {provider_name: success}
        """
        import asyncio
        
        if not self.providers:
            return {}
        
        async def test_provider(provider: NotificationProvider) -> tuple:
            try:
                result = await provider.test()
                return (provider.name, result)
            except Exception:
                return (provider.name, False)
        
        tasks = [test_provider(p) for p in self.providers]
        results_list = await asyncio.gather(*tasks)
        
        return dict(results_list)
