"""
浏览器管理器 - 使用 Playwright 进行浏览器自动化
"""
import asyncio
import logging
import random
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Error as PlaywrightError
)


logger = logging.getLogger(__name__)


# 常用 User-Agent 列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class BrowserConfig:
    """浏览器配置"""
    headless: bool = True
    timeout: int = 30000
    slow_mo: int = 0
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    timezone_id: str = "America/New_York"
    proxy: Optional[str] = None
    user_agent: Optional[str] = None
    extra_args: List[str] = field(default_factory=list)


class BrowserManager:
    """浏览器管理器"""
    
    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        config: Optional[BrowserConfig] = None
    ):
        """
        初始化浏览器管理器
        
        Args:
            headless: 是否无头模式
            timeout: 超时时间（毫秒）
            proxy: 代理地址
            user_agent: 自定义 User-Agent
            config: 完整的浏览器配置（优先级最高）
        """
        if config:
            self.config = config
        else:
            self.config = BrowserConfig(
                headless=headless,
                timeout=timeout,
                proxy=proxy,
                user_agent=user_agent
            )
        
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page_pool: List[Page] = []
        self._lock = asyncio.Lock()
        self._initialized = False
    
    @property
    def timeout(self) -> int:
        """获取超时时间"""
        return self.config.timeout
    
    async def initialize(self):
        """初始化浏览器"""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            logger.info("初始化浏览器...")
            
            self._playwright = await async_playwright().start()
            
            # 浏览器启动参数
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ]
            launch_args.extend(self.config.extra_args)
            
            # 代理配置
            proxy_config = None
            if self.config.proxy:
                proxy_config = {"server": self.config.proxy}
                logger.info(f"使用代理: {self.config.proxy}")
            
            # 启动浏览器
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo,
                args=launch_args,
                proxy=proxy_config
            )
            
            # 创建浏览器上下文
            self._context = await self._create_context()
            
            self._initialized = True
            logger.info("浏览器初始化完成")
    
    async def _create_context(self) -> BrowserContext:
        """创建浏览器上下文"""
        user_agent = self.config.user_agent or random.choice(USER_AGENTS)
        
        context = await self._browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height
            },
            user_agent=user_agent,
            locale=self.config.locale,
            timezone_id=self.config.timezone_id,
            # 反检测设置
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
            # 权限
            permissions=["geolocation"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060},  # New York
        )
        
        # 注入反检测脚本
        await context.add_init_script(self._get_stealth_script())
        
        return context
    
    def _get_stealth_script(self) -> str:
        """获取反检测脚本"""
        return """
        // 隐藏 webdriver 属性
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // 修改 navigator.plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {
                    0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                    description: "Portable Document Format",
                    filename: "internal-pdf-viewer",
                    length: 1,
                    name: "Chrome PDF Plugin"
                },
                {
                    0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                    description: "Portable Document Format",
                    filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                    length: 1,
                    name: "Chrome PDF Viewer"
                }
            ]
        });
        
        // 修改 navigator.languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        
        // 修改 navigator.platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });
        
        // 隐藏自动化相关属性
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        
        // 修改 chrome 对象
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // 修改 permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        
        // 修改 WebGL 渲染器信息
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter.apply(this, arguments);
        };
        """
    
    async def get_new_page(self) -> Page:
        """获取新页面"""
        await self.initialize()
        
        page = await self._context.new_page()
        
        # 设置默认超时
        page.set_default_timeout(self.config.timeout)
        page.set_default_navigation_timeout(self.config.timeout)
        
        return page
    
    @asynccontextmanager
    async def get_page(self):
        """获取页面的上下文管理器"""
        page = await self.get_new_page()
        try:
            yield page
        finally:
            await page.close()
    
    async def close_page(self, page: Page):
        """关闭页面"""
        try:
            await page.close()
        except PlaywrightError as e:
            logger.warning(f"关闭页面失败: {e}")
    
    async def refresh_context(self):
        """刷新浏览器上下文（清除 cookies 等）"""
        async with self._lock:
            old_context = self._context
            try:
                # 先创建新的上下文
                self._context = await self._create_context()
                logger.info("浏览器上下文已刷新")
            except Exception as e:
                # 如果创建失败，保留旧的上下文
                logger.error(f"刷新上下文失败: {e}")
                raise
            finally:
                # 关闭旧的上下文
                if old_context:
                    try:
                        await old_context.close()
                    except Exception as e:
                        logger.warning(f"关闭旧上下文失败: {e}")
    
    async def set_cookies(self, cookies: List[Dict[str, Any]]):
        """设置 cookies"""
        await self.initialize()
        await self._context.add_cookies(cookies)
    
    async def get_cookies(self) -> List[Dict[str, Any]]:
        """获取 cookies"""
        await self.initialize()
        return await self._context.cookies()
    
    async def clear_cookies(self):
        """清除 cookies"""
        await self.initialize()
        await self._context.clear_cookies()
    
    async def screenshot(self, page: Page, path: str):
        """截图"""
        await page.screenshot(path=path, full_page=True)
        logger.info(f"截图已保存: {path}")
    
    async def close(self):
        """关闭浏览器"""
        async with self._lock:
            if self._context:
                await self._context.close()
                self._context = None
            
            if self._browser:
                await self._browser.close()
                self._browser = None
            
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            
            self._initialized = False
            logger.info("浏览器已关闭")
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class PageHelper:
    """页面辅助工具"""
    
    @staticmethod
    async def wait_for_cloudflare(page: Page, timeout: int = 30000) -> bool:
        """
        等待 Cloudflare 验证完成
        
        Args:
            page: 页面对象
            timeout: 超时时间（毫秒）
            
        Returns:
            是否成功通过验证
        """
        try:
            # 等待 Cloudflare 验证页面消失
            await page.wait_for_function(
                """
                () => {
                    const title = document.title.toLowerCase();
                    const body = document.body ? document.body.innerText.toLowerCase() : '';
                    
                    // 检查是否还在验证页面
                    const isChallenge = 
                        title.includes('just a moment') ||
                        title.includes('attention required') ||
                        title.includes('checking your browser') ||
                        body.includes('checking your browser') ||
                        body.includes('please wait') ||
                        document.querySelector('#challenge-running') !== null ||
                        document.querySelector('.cf-browser-verification') !== null;
                    
                    return !isChallenge;
                }
                """,
                timeout=timeout
            )
            return True
        except PlaywrightError:
            return False
    
    @staticmethod
    async def is_cloudflare_challenge(page: Page) -> bool:
        """检查是否是 Cloudflare 验证页面"""
        try:
            return await page.evaluate(
                """
                () => {
                    const title = document.title.toLowerCase();
                    const body = document.body ? document.body.innerText.toLowerCase() : '';
                    
                    return (
                        title.includes('just a moment') ||
                        title.includes('attention required') ||
                        title.includes('checking your browser') ||
                        body.includes('checking your browser') ||
                        body.includes('please wait') ||
                        document.querySelector('#challenge-running') !== null ||
                        document.querySelector('.cf-browser-verification') !== null ||
                        document.querySelector('iframe[src*="challenges.cloudflare.com"]') !== null
                    );
                }
                """
            )
        except PlaywrightError:
            return False
    
    @staticmethod
    async def get_turnstile_sitekey(page: Page) -> Optional[str]:
        """获取 Turnstile sitekey"""
        try:
            return await page.evaluate(
                """
                () => {
                    // 从 iframe src 获取
                    const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                    if (iframe) {
                        const src = iframe.src;
                        const match = src.match(/[?&]k=([^&]+)/);
                        if (match) return match[1];
                    }
                    
                    // 从 data 属性获取
                    const widget = document.querySelector('[data-sitekey]');
                    if (widget) {
                        return widget.getAttribute('data-sitekey');
                    }
                    
                    // 从 turnstile 容器获取
                    const container = document.querySelector('.cf-turnstile');
                    if (container) {
                        return container.getAttribute('data-sitekey');
                    }
                    
                    return null;
                }
                """
            )
        except PlaywrightError:
            return None
    
    @staticmethod
    async def random_delay(min_ms: int = 500, max_ms: int = 2000):
        """随机延迟"""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)
    
    @staticmethod
    async def human_like_scroll(page: Page):
        """模拟人类滚动行为"""
        await page.evaluate(
            """
            async () => {
                const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                const scrollHeight = document.body.scrollHeight;
                const viewportHeight = window.innerHeight;
                
                let currentPosition = 0;
                while (currentPosition < scrollHeight - viewportHeight) {
                    const scrollAmount = Math.random() * 200 + 100;
                    currentPosition += scrollAmount;
                    window.scrollTo(0, currentPosition);
                    await delay(Math.random() * 200 + 100);
                }
            }
            """
        )
    
    @staticmethod
    async def human_like_type(page: Page, selector: str, text: str):
        """模拟人类输入"""
        element = await page.query_selector(selector)
        if element:
            for char in text:
                await element.type(char, delay=random.randint(50, 150))
                await asyncio.sleep(random.random() * 0.1)
