"""
VPS 库存监控引擎
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Callable, Any, Union
from dataclasses import dataclass, field

from playwright.async_api import Page

from ..config.settings import ConfigManager, get_config
from ..config.products import Product, ProductStatus, StockStatus
from ..captcha.capmonster import CapMonsterClient
from ..captcha.solver import CaptchaSolver
from ..notifications.base import NotificationMessage, NotificationLevel, NotificationManager
from ..utils.affiliate import get_affiliate_url
from .browser import BrowserManager


logger = logging.getLogger(__name__)


@dataclass
class MonitorResult:
    """监控结果"""
    product: Product
    status: StockStatus
    changed: bool = False
    notified: bool = False
    duration_ms: int = 0


class VPSMonitor:
    """VPS 库存监控器"""
    
    def __init__(
        self,
        browser: BrowserManager,
        capmonster: Optional[CapMonsterClient] = None,
        notification_manager: Optional[NotificationManager] = None,
        config: Optional[ConfigManager] = None
    ):
        """
        初始化监控器
        
        Args:
            browser: 浏览器管理器
            capmonster: CapMonster 客户端（可选）
            notification_manager: 通知管理器（可选）
            config: 配置管理器（可选，默认使用全局配置）
        """
        self.browser = browser
        self.capmonster = capmonster
        self.notification_manager = notification_manager
        self.config = config or get_config()
        self.captcha_solver = CaptchaSolver(capmonster) if capmonster else None
        
        # 状态缓存
        self._status_cache: Dict[str, ProductStatus] = {}
        self._last_check: Dict[str, datetime] = {}
        
        # 回调函数
        self._on_stock_change: Optional[Callable[[StockStatus], Any]] = None
        self._on_check_complete: Optional[Callable[[MonitorResult], Any]] = None
    
    def on_stock_change(self, callback: Callable[[StockStatus], Any]):
        """注册库存变化回调"""
        self._on_stock_change = callback
    
    def on_check_complete(self, callback: Callable[[MonitorResult], Any]):
        """注册检查完成回调"""
        self._on_check_complete = callback
    
    async def check_product(self, product: Product) -> StockStatus:
        """
        检查单个产品的库存状态
        
        Args:
            product: 产品对象
            
        Returns:
            库存状态
        """
        start_time = datetime.now()
        
        try:
            async with self.browser.get_page() as page:
                # 访问产品页面
                logger.info(f"检查产品: {product.name}")
                
                response = await page.goto(
                    product.url,
                    wait_until="domcontentloaded",
                    timeout=self.browser.timeout
                )
                
                if not response:
                    return StockStatus(
                        product=product,
                        status=ProductStatus.ERROR,
                        error_message="无法加载页面"
                    )
                
                # 检测并处理验证码
                if self.captcha_solver:
                    captcha_type, sitekey = await self.captcha_solver.detect_captcha_type(page)
                    
                    if captcha_type:
                        logger.info(f"检测到验证码: {captcha_type}")
                        result = await self.captcha_solver.solve(
                            page, product.url, captcha_type, sitekey
                        )
                        
                        if result.success and result.token:
                            await self.captcha_solver.inject_token(
                                page, result.token, captcha_type
                            )
                            # 等待页面刷新
                            await asyncio.sleep(2)
                            await page.wait_for_load_state("networkidle")
                        else:
                            logger.warning(f"验证码解决失败: {result.error_description}")
                
                # 等待页面加载完成
                await page.wait_for_load_state("networkidle", timeout=10000)
                
                # 解析库存状态
                status = await self._parse_stock_status(page, product)
                
                # 记录检查时间
                status.checked_at = datetime.now().isoformat()
                
                return status
                
        except Exception as e:
            logger.error(f"检查产品失败 [{product.name}]: {e}")
            return StockStatus(
                product=product,
                status=ProductStatus.ERROR,
                error_message=str(e),
                checked_at=datetime.now().isoformat()
            )
    
    async def _parse_stock_status(self, page: Page, product: Product) -> StockStatus:
        """解析页面中的库存状态"""
        site_config = self.config.get_site_config(product.site)
        
        # 获取页面内容
        content = await page.content()
        content_lower = content.lower()
        
        # 检查缺货标识
        out_of_stock_indicators = [
            site_config.out_of_stock_text.lower(),
            "out of stock",
            "sold out",
            "unavailable",
            "not available",
            "缺货",
            "已售罄",
            "暂无库存"
        ]
        
        is_out_of_stock = any(
            indicator in content_lower
            for indicator in out_of_stock_indicators
        )
        
        # 检查有货标识
        in_stock_indicators = [
            "add to cart",
            "order now",
            "buy now",
            "in stock",
            "available",
            "立即购买",
            "加入购物车",
            "有货"
        ]
        
        is_in_stock = any(
            indicator in content_lower
            for indicator in in_stock_indicators
        )
        
        # 尝试获取库存文本
        stock_text = None
        try:
            stock_element = await page.query_selector(site_config.stock_selector)
            if stock_element:
                stock_text = await stock_element.inner_text()
        except Exception:
            pass
        
        # 尝试获取价格
        price = None
        if site_config.price_selector:
            try:
                price_element = await page.query_selector(site_config.price_selector)
                if price_element:
                    price_text = await price_element.inner_text()
                    price = self._parse_price(price_text)
            except Exception:
                pass
        
        # 确定状态
        if is_out_of_stock and not is_in_stock:
            status = ProductStatus.OUT_OF_STOCK
        elif is_in_stock:
            status = ProductStatus.IN_STOCK
        else:
            # 无法确定，默认为缺货
            status = ProductStatus.OUT_OF_STOCK
        
        return StockStatus(
            product=product,
            status=status,
            price=price,
            stock_text=stock_text
        )
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """解析价格文本"""
        import re
        
        # 移除货币符号和空格
        cleaned = re.sub(r'[^\d.,]', '', price_text)
        
        # 处理不同的数字格式
        if ',' in cleaned and '.' in cleaned:
            # 1,234.56 格式
            cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            # 可能是 1234,56 格式（欧洲）或 1,234 格式
            parts = cleaned.split(',')
            if len(parts) == 2 and len(parts[1]) == 2:
                cleaned = cleaned.replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    async def check_products(
        self,
        products: List[Product],
        concurrent: int = 1
    ) -> List[MonitorResult]:
        """
        批量检查产品
        
        Args:
            products: 产品列表
            concurrent: 并发数
            
        Returns:
            监控结果列表
        """
        results: List[MonitorResult] = []
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrent)
        
        async def check_with_semaphore(product: Product) -> MonitorResult:
            async with semaphore:
                start_time = datetime.now()
                status = await self.check_product(product)
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # 检查状态是否变化
                old_status = self._status_cache.get(product.url)
                changed = old_status != status.status
                
                # 更新缓存
                self._status_cache[product.url] = status.status
                self._last_check[product.url] = datetime.now()
                
                result = MonitorResult(
                    product=product,
                    status=status,
                    changed=changed,
                    duration_ms=duration
                )
                
                # 触发回调
                if changed and status.in_stock:
                    if self._on_stock_change:
                        await self._on_stock_change(status)
                    
                    # 发送通知
                    if self.notification_manager:
                        await self._send_notification(status)
                        result.notified = True
                
                if self._on_check_complete:
                    await self._on_check_complete(result)
                
                return result
        
        # 过滤出启用的产品
        enabled_products = [p for p in products if p.enabled]
        
        # 并发执行检查
        tasks = [check_with_semaphore(p) for p in enabled_products]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # 使用 enabled_products 而不是 products，确保索引对应
                logger.error(f"检查产品异常: {enabled_products[i].name}, {result}")
                final_results.append(MonitorResult(
                    product=enabled_products[i],
                    status=StockStatus(
                        product=enabled_products[i],
                        status=ProductStatus.ERROR,
                        error_message=str(result)
                    ),
                    changed=False
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    async def _send_notification(self, status: StockStatus):
        """发送库存通知"""
        product = status.product
        
        # 获取带 Affiliate 参数的链接
        affiliate_url = get_affiliate_url(product.url)
        
        # 构建通知消息
        body_lines = [
            f"📦 产品: {product.name}",
            f"📝 描述: {product.description}",
        ]
        
        if status.price:
            body_lines.append(f"💰 价格: ${status.price:.2f}")
        
        if status.stock_text:
            body_lines.append(f"📊 状态: {status.stock_text}")
        
        body_lines.extend([
            "",
            f"🔗 链接: {affiliate_url}",
            "",
            "⏰ 快去抢购吧！"
        ])
        
        message = NotificationMessage(
            title="🎉 VPS 补货通知",
            body="\n".join(body_lines),
            level=NotificationLevel.SUCCESS,
            url=affiliate_url
        )
        
        # 发送到所有通知渠道
        await self.notification_manager.send_all(message)
    
    def get_status(self, product_url: str) -> Optional[ProductStatus]:
        """获取产品的缓存状态"""
        return self._status_cache.get(product_url)
    
    def get_last_check(self, product_url: str) -> Optional[datetime]:
        """获取产品的最后检查时间"""
        return self._last_check.get(product_url)
    
    def clear_cache(self):
        """清除状态缓存"""
        self._status_cache.clear()
        self._last_check.clear()
