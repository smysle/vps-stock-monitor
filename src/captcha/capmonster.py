"""
CapMonster Cloud API 客户端
支持 Turnstile 和 AntiCloudflare 任务
"""
import time
import asyncio
import aiohttp
from aiohttp import ClientError, ClientResponseError
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


logger = logging.getLogger(__name__)


class CaptchaError(Exception):
    """验证码服务基础异常"""
    pass


class CaptchaNetworkError(CaptchaError):
    """网络错误"""
    pass


class CaptchaRateLimitError(CaptchaError):
    """速率限制错误"""
    pass


class CaptchaTimeoutError(CaptchaError):
    """超时错误"""
    pass


class CaptchaTaskError(CaptchaError):
    """任务错误"""
    pass


class TaskType(Enum):
    """CapMonster 任务类型"""
    TURNSTILE = "TurnstileTask"
    TURNSTILE_PROXYLESS = "TurnstileTaskProxyless"
    ANTI_CLOUDFLARE = "AntiCloudflareTask"
    RECAPTCHA_V2 = "RecaptchaV2Task"
    RECAPTCHA_V2_PROXYLESS = "RecaptchaV2TaskProxyless"
    HCAPTCHA = "HCaptchaTask"
    HCAPTCHA_PROXYLESS = "HCaptchaTaskProxyless"


@dataclass
class TaskResult:
    """任务结果"""
    success: bool
    token: Optional[str] = None
    user_agent: Optional[str] = None
    cookies: Optional[Dict[str, str]] = None
    error_code: Optional[str] = None
    error_description: Optional[str] = None


class CapMonsterClient:
    """CapMonster Cloud API 客户端"""
    
    BASE_URL = "https://api.capmonster.cloud"
    
    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(
        self,
        api_key: str,
        timeout: int = 120,
        poll_interval: int = 3
    ):
        if not api_key or not isinstance(api_key, str):
            raise ValueError("API Key 不能为空")
        
        api_key = api_key.strip()
        if len(api_key) < 20:
            logger.warning("API Key 长度异常，请检查配置")
        
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._session: Optional[aiohttp.ClientSession] = None
    
    def __repr__(self) -> str:
        key_hint = f"{self.api_key[:4]}***" if self.api_key else ""
        return f"CapMonsterClient(api_key='{key_hint}', timeout={self.timeout})"
    
    async def __aenter__(self):
        """支持 async with 语法"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """自动关闭会话"""
        await self.close()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def close(self):
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def _make_request(
        self, 
        endpoint: str, 
        payload: Dict[str, Any],
        retries: int = MAX_RETRIES
    ) -> Dict[str, Any]:
        """发起 HTTP 请求（带重试和异常处理）"""
        session = await self._get_session()
        last_error = None
        
        for attempt in range(retries):
            try:
                async with session.post(
                    f"{self.BASE_URL}/{endpoint}",
                    json=payload
                ) as resp:
                    # 检查 HTTP 状态码
                    if resp.status == 429:
                        retry_after = int(resp.headers.get('Retry-After', 5))
                        raise CaptchaRateLimitError(f"API 限流，需等待 {retry_after} 秒")
                    
                    if resp.status >= 500:
                        raise CaptchaNetworkError(f"服务器错误: HTTP {resp.status}")
                    
                    if resp.status >= 400:
                        # 不暴露响应内容，可能包含敏感信息
                        raise CaptchaTaskError(f"请求失败: HTTP {resp.status}")
                    
                    try:
                        data = await resp.json()
                    except Exception:
                        raise CaptchaNetworkError("响应不是有效的 JSON")
                    
                    return data
                    
            except CaptchaRateLimitError:
                # 限流错误，等待后重试
                if attempt < retries - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue
                raise
                
            except (ClientError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < retries - 1:
                    logger.warning(f"请求失败 (尝试 {attempt + 1}/{retries}): {type(e).__name__}")
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                    continue
                raise CaptchaNetworkError(f"网络错误: {type(e).__name__}") from e
                
            except CaptchaError:
                raise
                
            except Exception as e:
                raise CaptchaNetworkError(f"未知错误: {e}") from e
        
        raise CaptchaNetworkError(f"请求失败，已重试 {retries} 次: {last_error}")
    
    async def get_balance(self) -> float:
        """获取账户余额"""
        data = await self._make_request(
            "getBalance",
            {"clientKey": self.api_key}
        )
        
        if data.get("errorId", 0) != 0:
            raise CaptchaTaskError(f"获取余额失败: {data.get('errorDescription')}")
        
        return data.get("balance", 0)
    
    async def create_task(self, task_data: Dict[str, Any]) -> int:
        """创建任务"""
        # 不记录包含敏感信息的完整 task_data
        logger.debug(f"创建任务: {task_data.get('type')}")
        
        data = await self._make_request(
            "createTask",
            {
                "clientKey": self.api_key,
                "task": task_data
            }
        )
        
        if data.get("errorId", 0) != 0:
            raise CaptchaTaskError(f"创建任务失败: {data.get('errorDescription')}")
        
        task_id = data.get("taskId")
        logger.info(f"任务已创建: {task_id}")
        return task_id
    
    async def get_task_result(self, task_id: int) -> Dict[str, Any]:
        """获取任务结果"""
        return await self._make_request(
            "getTaskResult",
            {
                "clientKey": self.api_key,
                "taskId": task_id
            }
        )
    
    async def wait_for_result(self, task_id: int) -> TaskResult:
        """等待任务完成并返回结果"""
        start_time = time.monotonic()
        
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > self.timeout:
                return TaskResult(
                    success=False,
                    error_code="TIMEOUT",
                    error_description=f"任务超时 ({self.timeout}秒)"
                )
            
            try:
                result = await self.get_task_result(task_id)
            except CaptchaError as e:
                return TaskResult(
                    success=False,
                    error_code="NETWORK_ERROR",
                    error_description=str(e)
                )
            
            if result.get("errorId", 0) != 0:
                return TaskResult(
                    success=False,
                    error_code=result.get("errorCode"),
                    error_description=result.get("errorDescription")
                )
            
            status = result.get("status")
            
            if status == "ready":
                solution = result.get("solution", {})
                return TaskResult(
                    success=True,
                    token=solution.get("token") or solution.get("cf_clearance"),
                    user_agent=solution.get("userAgent"),
                    cookies=solution.get("cookies")
                )
            
            logger.debug(f"任务 {task_id} 状态: {status}, 等待中...")
            await asyncio.sleep(self.poll_interval)
    
    async def solve_turnstile(
        self,
        website_url: str,
        website_key: str,
        action: Optional[str] = None,
        data: Optional[str] = None,
        use_proxy: bool = False,
        proxy_type: Optional[str] = None,
        proxy_address: Optional[str] = None,
        proxy_port: Optional[int] = None,
        proxy_login: Optional[str] = None,
        proxy_password: Optional[str] = None
    ) -> TaskResult:
        """
        解决 Cloudflare Turnstile 验证
        
        Args:
            website_url: 目标网站 URL
            website_key: Turnstile sitekey
            action: 可选的 action 参数
            data: 可选的 data 参数
            use_proxy: 是否使用代理
            proxy_*: 代理配置
        """
        task_data = {
            "type": TaskType.TURNSTILE.value if use_proxy else TaskType.TURNSTILE_PROXYLESS.value,
            "websiteURL": website_url,
            "websiteKey": website_key
        }
        
        if action:
            task_data["turnstileAction"] = action
        if data:
            task_data["turnstileData"] = data
        
        if use_proxy and proxy_address:
            task_data.update({
                "proxyType": proxy_type or "http",
                "proxyAddress": proxy_address,
                "proxyPort": proxy_port,
                "proxyLogin": proxy_login,
                "proxyPassword": proxy_password
            })
        
        task_id = await self.create_task(task_data)
        return await self.wait_for_result(task_id)
    
    async def solve_cloudflare_challenge(
        self,
        website_url: str,
        proxy_type: str = "http",
        proxy_address: str = "",
        proxy_port: int = 0,
        proxy_login: Optional[str] = None,
        proxy_password: Optional[str] = None,
        html_page_base64: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> TaskResult:
        """
        解决 Cloudflare 5秒盾/Challenge 页面
        
        这个任务类型会返回 cf_clearance cookie 和 userAgent
        需要使用返回的 cookie 和 userAgent 来访问目标网站
        
        Args:
            website_url: 目标网站 URL
            proxy_*: 代理配置 (必需)
            html_page_base64: 可选的 HTML 页面 base64 编码
            user_agent: 可选的 User-Agent
        """
        task_data = {
            "type": TaskType.ANTI_CLOUDFLARE.value,
            "websiteURL": website_url,
            "proxyType": proxy_type,
            "proxyAddress": proxy_address,
            "proxyPort": proxy_port
        }
        
        if proxy_login:
            task_data["proxyLogin"] = proxy_login
        if proxy_password:
            task_data["proxyPassword"] = proxy_password
        if html_page_base64:
            task_data["htmlPageBase64"] = html_page_base64
        if user_agent:
            task_data["userAgent"] = user_agent
        
        task_id = await self.create_task(task_data)
        return await self.wait_for_result(task_id)
    
    async def solve_recaptcha_v2(
        self,
        website_url: str,
        website_key: str,
        use_proxy: bool = False,
        proxy_type: Optional[str] = None,
        proxy_address: Optional[str] = None,
        proxy_port: Optional[int] = None,
        proxy_login: Optional[str] = None,
        proxy_password: Optional[str] = None
    ) -> TaskResult:
        """解决 reCAPTCHA v2"""
        task_data = {
            "type": TaskType.RECAPTCHA_V2.value if use_proxy else TaskType.RECAPTCHA_V2_PROXYLESS.value,
            "websiteURL": website_url,
            "websiteKey": website_key
        }
        
        if use_proxy and proxy_address:
            task_data.update({
                "proxyType": proxy_type or "http",
                "proxyAddress": proxy_address,
                "proxyPort": proxy_port,
                "proxyLogin": proxy_login,
                "proxyPassword": proxy_password
            })
        
        task_id = await self.create_task(task_data)
        return await self.wait_for_result(task_id)
    
    async def solve_hcaptcha(
        self,
        website_url: str,
        website_key: str,
        use_proxy: bool = False,
        proxy_type: Optional[str] = None,
        proxy_address: Optional[str] = None,
        proxy_port: Optional[int] = None,
        proxy_login: Optional[str] = None,
        proxy_password: Optional[str] = None
    ) -> TaskResult:
        """解决 hCaptcha"""
        task_data = {
            "type": TaskType.HCAPTCHA.value if use_proxy else TaskType.HCAPTCHA_PROXYLESS.value,
            "websiteURL": website_url,
            "websiteKey": website_key
        }
        
        if use_proxy and proxy_address:
            task_data.update({
                "proxyType": proxy_type or "http",
                "proxyAddress": proxy_address,
                "proxyPort": proxy_port,
                "proxyLogin": proxy_login,
                "proxyPassword": proxy_password
            })
        
        task_id = await self.create_task(task_data)
        return await self.wait_for_result(task_id)
