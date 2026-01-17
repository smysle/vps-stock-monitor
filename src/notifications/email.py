"""
邮件通知
"""
import html as html_module
import asyncio
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .base import NotificationProvider, NotificationMessage, NotificationLevel


logger = logging.getLogger(__name__)

# 共享线程池用于 SMTP 操作
_smtp_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="smtp")


def _validate_url(url: str) -> bool:
    """验证 URL 是否安全"""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


class EmailNotifier(NotificationProvider):
    """邮件通知器"""
    
    # 通知级别对应的 emoji
    LEVEL_EMOJI = {
        NotificationLevel.INFO: "ℹ️",
        NotificationLevel.SUCCESS: "✅",
        NotificationLevel.WARNING: "⚠️",
        NotificationLevel.ERROR: "❌",
    }
    
    # 配置
    SMTP_TIMEOUT = 30
    MAX_RETRIES = 2
    
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: List[str],
        use_tls: bool = True,
        use_ssl: bool = False
    ):
        """
        初始化邮件通知器
        
        Args:
            smtp_host: SMTP 服务器地址
            smtp_port: SMTP 端口
            username: SMTP 用户名
            password: SMTP 密码
            from_email: 发件人邮箱
            to_emails: 收件人邮箱列表
            use_tls: 是否使用 STARTTLS
            use_ssl: 是否使用 SSL
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self._password = password  # 私有属性
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls
        self.use_ssl = use_ssl
    
    def __repr__(self) -> str:
        """安全的字符串表示（不暴露密码）"""
        return f"EmailNotifier(from={self.from_email}, to={len(self.to_emails)} recipients)"
    
    @property
    def name(self) -> str:
        return "email"
    
    def _build_html_body(self, message: NotificationMessage) -> str:
        """构建 HTML 邮件正文（安全转义）"""
        emoji = self.LEVEL_EMOJI.get(message.level, "")
        
        # 安全转义用户输入
        safe_title = html_module.escape(message.title)
        safe_body = html_module.escape(message.body).replace('\n', '<br>')
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background: #f9f9f9;
                    padding: 20px;
                    border: 1px solid #ddd;
                    border-top: none;
                    border-radius: 0 0 8px 8px;
                }}
                .button {{
                    display: inline-block;
                    background: #667eea;
                    color: white;
                    padding: 10px 20px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 15px;
                }}
                .tags {{
                    margin-top: 15px;
                    color: #666;
                    font-size: 0.9em;
                }}
                .footer {{
                    margin-top: 20px;
                    text-align: center;
                    color: #999;
                    font-size: 0.8em;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{emoji} {safe_title}</h2>
            </div>
            <div class="content">
                <p>{safe_body}</p>
        """
        
        # URL 验证后再添加
        if message.url and _validate_url(message.url):
            safe_url = html_module.escape(message.url)
            html += f'<a href="{safe_url}" class="button">查看详情</a>'
        
        if message.tags:
            safe_tags = [html_module.escape(t) for t in message.tags if t and len(t) < 50]
            html += f'<div class="tags">标签: {", ".join(safe_tags)}</div>'
        
        html += f"""
            </div>
            <div class="footer">
                <p>此邮件由 VPS 库存监控系统自动发送</p>
                <p>{message.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _send_sync(self, msg: MIMEMultipart) -> bool:
        """同步发送邮件（在线程池中执行）"""
        for attempt in range(self.MAX_RETRIES):
            try:
                if self.use_ssl:
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(
                        self.smtp_host, 
                        self.smtp_port, 
                        context=context,
                        timeout=self.SMTP_TIMEOUT
                    ) as server:
                        server.login(self.username, self._password)
                        server.sendmail(
                            self.from_email, self.to_emails, msg.as_string()
                        )
                else:
                    with smtplib.SMTP(
                        self.smtp_host, 
                        self.smtp_port,
                        timeout=self.SMTP_TIMEOUT
                    ) as server:
                        if self.use_tls:
                            server.starttls()
                        server.login(self.username, self._password)
                        server.sendmail(
                            self.from_email, self.to_emails, msg.as_string()
                        )
                return True
                
            except (smtplib.SMTPException, OSError) as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"邮件发送失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    continue
                raise
        
        return False
    
    async def send(self, message: NotificationMessage) -> bool:
        """发送邮件（异步执行）"""
        try:
            # 创建邮件
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"{self.LEVEL_EMOJI.get(message.level, '')} {message.title}"
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            
            # 添加纯文本和 HTML 版本
            text_part = MIMEText(message.to_text(), "plain", "utf-8")
            html_part = MIMEText(self._build_html_body(message), "html", "utf-8")
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # 在线程池中异步执行 SMTP 操作，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(_smtp_executor, self._send_sync, msg)
            
            if result:
                logger.info(f"邮件发送成功: {message.title}")
            return result
            
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False
    
    def _test_connection_sync(self) -> bool:
        """同步测试连接（在线程池中执行）"""
        if self.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self.smtp_host, 
                self.smtp_port, 
                context=context,
                timeout=self.SMTP_TIMEOUT
            ) as server:
                server.login(self.username, self._password)
        else:
            with smtplib.SMTP(
                self.smtp_host, 
                self.smtp_port,
                timeout=self.SMTP_TIMEOUT
            ) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self._password)
        return True
    
    async def test(self) -> bool:
        """测试邮件连接（异步执行）"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(_smtp_executor, self._test_connection_sync)
            
            if result:
                logger.info("邮件服务器连接成功")
            return result
            
        except Exception as e:
            logger.error(f"邮件服务器连接失败: {e}")
            return False
