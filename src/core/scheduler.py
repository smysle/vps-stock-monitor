"""
任务调度器
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from ..config.settings import ConfigManager, get_config
from ..config.products import Product, get_enabled_products
from .monitor import VPSMonitor, MonitorResult


logger = logging.getLogger(__name__)


class SchedulerState(Enum):
    """调度器状态"""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class SchedulerStats:
    """调度器统计"""
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    stock_alerts: int = 0
    last_check_time: Optional[datetime] = None
    next_check_time: Optional[datetime] = None
    uptime_seconds: int = 0
    start_time: Optional[datetime] = None


class MonitorScheduler:
    """监控调度器"""
    
    def __init__(
        self,
        monitor: VPSMonitor,
        products: Optional[List[Product]] = None,
        check_interval: int = 300,
        retry_interval: int = 60,
        max_retries: int = 3,
        config: Optional[ConfigManager] = None
    ):
        """
        初始化调度器
        
        Args:
            monitor: VPS 监控器
            products: 产品列表（可选）
            check_interval: 检查间隔（秒）
            retry_interval: 重试间隔（秒）
            max_retries: 最大重试次数
            config: 配置管理器（可选）
        """
        self.monitor = monitor
        self._products = products or get_enabled_products()
        self.check_interval = check_interval
        self.retry_interval = retry_interval
        self.max_retries = max_retries
        self.config = config or get_config()
        
        self._state = SchedulerState.STOPPED
        self._task: Optional[asyncio.Task] = None
        self._stats = SchedulerStats()
        self._callbacks: List[Callable[[MonitorResult], Any]] = []
        self._stop_event = asyncio.Event()
        self._products_lock = asyncio.Lock()  # 保护 products 的锁
    
    @property
    def state(self) -> SchedulerState:
        return self._state
    
    @property
    def stats(self) -> SchedulerStats:
        if self._stats.start_time:
            self._stats.uptime_seconds = int(
                (datetime.now() - self._stats.start_time).total_seconds()
            )
        return self._stats
    
    def add_callback(self, callback: Callable[[MonitorResult], Any]):
        """添加结果回调"""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[MonitorResult], Any]):
        """移除结果回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    async def start(self):
        """启动调度器"""
        if self._state == SchedulerState.RUNNING:
            logger.warning("调度器已在运行中")
            return
        
        logger.info("启动监控调度器...")
        self._state = SchedulerState.RUNNING
        self._stats.start_time = datetime.now()
        self._stop_event.clear()
        
        self._task = asyncio.create_task(self._run_loop())
    
    async def stop(self):
        """停止调度器"""
        if self._state == SchedulerState.STOPPED:
            return
        
        logger.info("停止监控调度器...")
        self._state = SchedulerState.STOPPED
        self._stop_event.set()
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
    
    async def pause(self):
        """暂停调度器"""
        if self._state == SchedulerState.RUNNING:
            self._state = SchedulerState.PAUSED
            logger.info("调度器已暂停")
    
    async def resume(self):
        """恢复调度器"""
        if self._state == SchedulerState.PAUSED:
            self._state = SchedulerState.RUNNING
            logger.info("调度器已恢复")
    
    def _get_check_interval(self) -> int:
        """获取当前检查间隔（支持热重载）"""
        # 优先使用配置文件中的值
        if self.config:
            return self.config.monitor.check_interval
        return self.check_interval
    
    def _get_retry_interval(self) -> int:
        """获取当前重试间隔（支持热重载）"""
        if self.config:
            return self.config.monitor.retry_interval
        return self.retry_interval
    
    async def _run_loop(self):
        """主循环"""
        while not self._stop_event.is_set():
            try:
                if self._state == SchedulerState.PAUSED:
                    await asyncio.sleep(1)
                    continue
                
                # 执行检查
                await self._run_check()
                
                # 获取当前检查间隔（支持热重载）
                interval = self._get_check_interval()
                
                # 更新下次检查时间
                self._stats.next_check_time = datetime.now() + timedelta(
                    seconds=interval
                )
                
                # 等待下次检查
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval
                    )
                except asyncio.TimeoutError:
                    pass
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"调度器循环异常: {e}")
                await asyncio.sleep(self._get_retry_interval())
    
    @property
    def products(self) -> List[Product]:
        """获取产品列表的副本"""
        return self._products.copy()
    
    async def _run_check(self):
        """执行一次检查"""
        # 支持热重载：从配置中获取最新的产品列表
        async with self._products_lock:
            if self.config:
                from ..config.settings import ProductConfig
                products_config = self.config.products
                if products_config:
                    # 转换配置中的产品
                    self._products = [
                        Product(
                            name=pc.name,
                            url=pc.url,
                            site=pc.site,
                            description=pc.description,
                            enabled=pc.enabled
                        )
                        for pc in products_config
                        if pc.enabled
                    ]
            
            if not self._products:
                self._products = get_enabled_products()
            
            # 创建当前检查的产品列表副本
            current_products = self._products.copy()
        
        if not current_products:
            logger.warning("没有可检查的产品")
            return
        
        logger.info(f"开始检查 {len(current_products)} 个产品...")
        self._stats.last_check_time = datetime.now()
        
        try:
            results = await self.monitor.check_products(
                current_products,
                concurrent=1  # 串行检查，避免被封
            )
            
            # 更新统计
            self._stats.total_checks += len(results)
            
            for result in results:
                if result.status.status.value == "error":
                    self._stats.failed_checks += 1
                else:
                    self._stats.successful_checks += 1
                
                if result.status.in_stock and result.changed:
                    self._stats.stock_alerts += 1
                
                # 触发回调
                await self._invoke_callbacks(result)
            
            logger.info(
                f"检查完成: 成功 {self._stats.successful_checks}, "
                f"失败 {self._stats.failed_checks}, "
                f"补货提醒 {self._stats.stock_alerts}"
            )
            
        except Exception as e:
            logger.error(f"检查执行失败: {e}")
            self._stats.total_checks += len(current_products)
            self._stats.failed_checks += len(current_products)
    
    async def _invoke_callbacks(self, result: MonitorResult):
        """安全地调用回调函数"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception as e:
                logger.error(f"回调执行失败 ({callback.__name__ if hasattr(callback, '__name__') else 'unknown'}): {e}")
    
    async def run_once(self) -> List[MonitorResult]:
        """执行一次检查（不启动循环）"""
        async with self._products_lock:
            current_products = self._products.copy()
        return await self.monitor.check_products(current_products)
    
    async def add_product(self, product: Product):
        """添加监控产品（线程安全）"""
        async with self._products_lock:
            if product not in self._products:
                self._products.append(product)
                logger.info(f"添加监控产品: {product.name}")
    
    async def remove_product(self, url: str):
        """移除监控产品（线程安全）"""
        async with self._products_lock:
            self._products = [p for p in self._products if p.url != url]
            logger.info(f"移除监控产品: {url}")
    
    def get_products(self) -> List[Product]:
        """获取监控产品列表"""
        return self._products.copy()
    
    def update_interval(self, interval: int):
        """更新检查间隔"""
        self.check_interval = interval
        logger.info(f"检查间隔已更新为: {interval} 秒")


class SchedulerManager:
    """调度器管理器 - 支持多个调度器"""
    
    def __init__(self):
        self._schedulers: dict[str, MonitorScheduler] = {}
    
    def add_scheduler(self, name: str, scheduler: MonitorScheduler):
        """添加调度器"""
        self._schedulers[name] = scheduler
    
    def get_scheduler(self, name: str) -> Optional[MonitorScheduler]:
        """获取调度器"""
        return self._schedulers.get(name)
    
    def remove_scheduler(self, name: str):
        """移除调度器"""
        if name in self._schedulers:
            del self._schedulers[name]
    
    async def start_all(self):
        """启动所有调度器"""
        for name, scheduler in self._schedulers.items():
            logger.info(f"启动调度器: {name}")
            await scheduler.start()
    
    async def stop_all(self):
        """停止所有调度器"""
        for name, scheduler in self._schedulers.items():
            logger.info(f"停止调度器: {name}")
            await scheduler.stop()
    
    def get_all_stats(self) -> dict[str, SchedulerStats]:
        """获取所有调度器统计"""
        return {name: s.stats for name, s in self._schedulers.items()}
