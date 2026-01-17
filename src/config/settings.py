"""
配置管理模块
支持 YAML 配置文件和热重载
"""
import os
import yaml
import logging
import threading
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent


logger = logging.getLogger(__name__)


@dataclass
class SiteConfig:
    """站点配置"""
    stock_selector: str
    out_of_stock_text: str
    price_selector: Optional[str] = None
    wait_time: int = 3000
    needs_browser: bool = True
    custom_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class TelegramConfig:
    """Telegram 配置"""
    enabled: bool = False
    bot_token: str = field(default="", repr=False)  # 不在repr中显示
    chat_id: str = ""
    parse_mode: str = "HTML"
    disable_preview: bool = False
    
    def __repr__(self) -> str:
        token_hint = "***" if self.bot_token else ""
        return f"TelegramConfig(enabled={self.enabled}, bot_token='{token_hint}', chat_id='{self.chat_id}')"


@dataclass
class DiscordConfig:
    """Discord 配置"""
    enabled: bool = False
    webhook_url: str = field(default="", repr=False)
    
    def __repr__(self) -> str:
        token_hint = "***" if self.webhook_url else ""
        return f"DiscordConfig(enabled={self.enabled}, webhook_url='{token_hint}')"


@dataclass
class EmailConfig:
    """邮件配置"""
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = field(default="", repr=False)
    from_addr: str = ""
    to_addrs: List[str] = field(default_factory=list)
    
    def __repr__(self) -> str:
        password_hint = "***" if self.smtp_password else ""
        return f"EmailConfig(enabled={self.enabled}, smtp_host='{self.smtp_host}', smtp_password='{password_hint}')"


@dataclass
class NotificationConfig:
    """通知配置"""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    email: EmailConfig = field(default_factory=EmailConfig)


@dataclass
class MonitorConfig:
    """监控配置"""
    check_interval: int = 300
    retry_interval: int = 60
    max_retries: int = 3
    concurrent_checks: int = 3


@dataclass
class BrowserConfig:
    """浏览器配置"""
    headless: bool = True
    timeout: int = 30000
    user_agent: str = ""


@dataclass
class ProxyConfig:
    """代理配置"""
    enabled: bool = False
    url: str = ""


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    file: str = "logs/monitor.log"
    max_size: int = 10485760  # 10MB
    backup_count: int = 5


@dataclass
class DataConfig:
    """数据存储配置"""
    dir: str = "./data"
    save_history: bool = True


@dataclass
class ProductConfig:
    """产品配置"""
    name: str
    url: str
    site: str
    enabled: bool = True
    description: str = ""
    check_interval: Optional[int] = None
    stock_selector: Optional[str] = None
    price_selector: Optional[str] = None
    out_of_stock_text: List[str] = field(default_factory=list)
    in_stock_text: List[str] = field(default_factory=list)
    notify_on_restock: bool = True
    notify_on_price_change: bool = False


# 默认站点配置
DEFAULT_SITE_CONFIGS: Dict[str, SiteConfig] = {
    "bandwagonhost.com": SiteConfig(
        stock_selector=".order-summary, .product-info, #order-boxes",
        out_of_stock_text="Out of Stock",
        price_selector=".product-price, .cycle-price",
        wait_time=3000
    ),
    "bwh81.net": SiteConfig(
        stock_selector=".order-summary, .product-info, #order-boxes",
        out_of_stock_text="Out of Stock",
        price_selector=".product-price, .cycle-price",
        wait_time=3000
    ),
    "dmit.io": SiteConfig(
        stock_selector=".product-stock-status, .order-summary, .product-info",
        out_of_stock_text="Out of Stock",
        price_selector=".product-price, .price",
        wait_time=3000
    ),
    "racknerd.com": SiteConfig(
        stock_selector=".product-status, .order-summary, .product-info",
        out_of_stock_text="Out of Stock",
        price_selector=".price, .product-price",
        wait_time=2000
    ),
    "cloudcone.com": SiteConfig(
        stock_selector=".product-status, .order-summary",
        out_of_stock_text="Out of Stock",
        price_selector=".price",
        wait_time=2000
    ),
}


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变更处理器"""
    
    def __init__(self, config_manager: 'ConfigManager'):
        self.config_manager = config_manager
        self._last_modified = 0
        self._debounce_seconds = 1  # 防抖时间
    
    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent):
            # 检查是否是配置文件
            if event.src_path.endswith(self.config_manager.config_file):
                current_time = time.time()
                # 防抖：避免重复触发
                if current_time - self._last_modified > self._debounce_seconds:
                    self._last_modified = current_time
                    logger.info(f"检测到配置文件变更: {event.src_path}")
                    self.config_manager.reload()


class ConfigManager:
    """
    配置管理器
    支持 YAML 配置文件和热重载
    """
    
    _instance: Optional['ConfigManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_file: str = "config.yaml"):
        # 避免重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self.config_file = config_file
        self._config_data: Dict[str, Any] = {}
        self._callbacks: List[Callable[['ConfigManager'], None]] = []
        self._observer: Optional[Observer] = None
        self._lock = threading.RLock()
        self._initialized = True
        
        # 加载配置
        self.load()
        
        # 缓存
        self._site_configs_cache: Optional[Dict[str, SiteConfig]] = None
        self._products_cache: Optional[List[ProductConfig]] = None
    
    def load(self) -> bool:
        """加载配置文件"""
        config_path = Path(self.config_file)
        
        if not config_path.exists():
            logger.warning(f"配置文件不存在: {self.config_file}，使用默认配置")
            self._config_data = {}
            return False
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config_data = yaml.safe_load(f) or {}
            logger.info(f"配置文件加载成功: {self.config_file}")
            return True
        except yaml.YAMLError as e:
            logger.error(f"配置文件解析错误: {e}")
            return False
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}")
            return False
    
    def reload(self) -> bool:
        """重新加载配置文件"""
        with self._lock:
            old_config = self._config_data.copy()
            
            if self.load():
                # 检查配置是否有变化
                if old_config != self._config_data:
                    # 清除缓存
                    self._site_configs_cache = None
                    self._products_cache = None
                    logger.info("配置已更新，触发回调...")
                    self._notify_callbacks()
                return True
            else:
                # 加载失败，恢复旧配置
                self._config_data = old_config
                return False
    
    def start_watching(self):
        """开始监听配置文件变更"""
        if self._observer is not None:
            return
        
        config_path = Path(self.config_file)
        watch_dir = str(config_path.parent.absolute()) or "."
        
        self._observer = Observer()
        handler = ConfigFileHandler(self)
        self._observer.schedule(handler, watch_dir, recursive=False)
        self._observer.start()
        
        logger.info(f"开始监听配置文件变更: {self.config_file}")
    
    def stop_watching(self):
        """停止监听配置文件变更"""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("停止监听配置文件变更")
    
    def on_config_change(self, callback: Callable[['ConfigManager'], None]):
        """注册配置变更回调"""
        self._callbacks.append(callback)
    
    def _notify_callbacks(self):
        """通知所有回调"""
        # 在持有锁的情况下复制回调列表
        with self._lock:
            callbacks = self._callbacks.copy()
        
        for callback in callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"配置变更回调执行失败: {e}")
    
    # ==================== 配置访问方法 ====================
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的路径（线程安全）"""
        with self._lock:
            keys = key.split('.')
            value = self._config_data
            
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
                
                if value is None:
                    return default
            
            return value
    
    @property
    def capmonster_api_key(self) -> str:
        """CapMonster API Key"""
        return self.get('capmonster.api_key', '')
    
    @property
    def notifications(self) -> NotificationConfig:
        """通知配置"""
        data = self.get('notifications', {})
        
        telegram_data = data.get('telegram', {})
        telegram = TelegramConfig(
            enabled=telegram_data.get('enabled', False),
            bot_token=telegram_data.get('bot_token', ''),
            chat_id=str(telegram_data.get('chat_id', '')),
            parse_mode=telegram_data.get('parse_mode', 'HTML'),
            disable_preview=telegram_data.get('disable_preview', False)
        )
        
        discord_data = data.get('discord', {})
        discord = DiscordConfig(
            enabled=discord_data.get('enabled', False),
            webhook_url=discord_data.get('webhook_url', '')
        )
        
        email_data = data.get('email', {})
        email = EmailConfig(
            enabled=email_data.get('enabled', False),
            smtp_host=email_data.get('smtp_host', 'smtp.gmail.com'),
            smtp_port=email_data.get('smtp_port', 587),
            smtp_user=email_data.get('smtp_user', ''),
            smtp_password=email_data.get('smtp_password', ''),
            from_addr=email_data.get('from_addr', ''),
            to_addrs=email_data.get('to_addrs', [])
        )
        
        return NotificationConfig(telegram=telegram, discord=discord, email=email)
    
    @property
    def monitor(self) -> MonitorConfig:
        """监控配置"""
        data = self.get('monitor', {})
        return MonitorConfig(
            check_interval=data.get('check_interval', 300),
            retry_interval=data.get('retry_interval', 60),
            max_retries=data.get('max_retries', 3),
            concurrent_checks=data.get('concurrent_checks', 3)
        )
    
    @property
    def browser(self) -> BrowserConfig:
        """浏览器配置"""
        data = self.get('browser', {})
        return BrowserConfig(
            headless=data.get('headless', True),
            timeout=data.get('timeout', 30000),
            user_agent=data.get('user_agent', '')
        )
    
    @property
    def proxy(self) -> ProxyConfig:
        """代理配置"""
        data = self.get('proxy', {})
        return ProxyConfig(
            enabled=data.get('enabled', False),
            url=data.get('url', '')
        )
    
    @property
    def affiliates(self) -> Dict[str, str]:
        """Affiliate 推广配置"""
        data = self.get('affiliates', {})
        # 过滤空值
        return {k: v for k, v in data.items() if v}
    
    @property
    def products(self) -> List[ProductConfig]:
        """产品列表"""
        data = self.get('products', [])
        products = []
        
        for item in data:
            if isinstance(item, dict):
                products.append(ProductConfig(
                    name=item.get('name', ''),
                    url=item.get('url', ''),
                    site=item.get('site', ''),
                    enabled=item.get('enabled', True),
                    description=item.get('description', ''),
                    check_interval=item.get('check_interval'),
                    stock_selector=item.get('stock_selector'),
                    price_selector=item.get('price_selector'),
                    out_of_stock_text=item.get('out_of_stock_text', []),
                    in_stock_text=item.get('in_stock_text', []),
                    notify_on_restock=item.get('notify_on_restock', True),
                    notify_on_price_change=item.get('notify_on_price_change', False)
                ))
        
        return products
    
    @property
    def site_configs(self) -> Dict[str, SiteConfig]:
        """站点配置（带缓存）"""
        if self._site_configs_cache is not None:
            return self._site_configs_cache
        
        configs = DEFAULT_SITE_CONFIGS.copy()
        
        data = self.get('sites', {})
        for site, config in data.items():
            if isinstance(config, dict):
                configs[site] = SiteConfig(
                    stock_selector=config.get('stock_selector', ''),
                    out_of_stock_text=config.get('out_of_stock_text', 'Out of Stock'),
                    price_selector=config.get('price_selector'),
                    wait_time=config.get('wait_time', 3000),
                    needs_browser=config.get('needs_browser', True),
                    custom_headers=config.get('custom_headers', {})
                )
        
        self._site_configs_cache = configs
        return configs
    
    def get_site_config(self, site: str) -> SiteConfig:
        """获取站点配置"""
        configs = self.site_configs
        
        # 精确匹配
        if site in configs:
            return configs[site]
        
        # 模糊匹配
        for domain, config in configs.items():
            if domain in site or site in domain:
                return config
        
        # 默认配置
        return SiteConfig(
            stock_selector=".order-summary, .product-info, .stock-status",
            out_of_stock_text="Out of Stock",
            price_selector=".price, .product-price",
            wait_time=3000
        )
    
    @property
    def logging_config(self) -> LoggingConfig:
        """日志配置"""
        data = self.get('logging', {})
        return LoggingConfig(
            level=data.get('level', 'INFO'),
            file=data.get('file', 'logs/monitor.log'),
            max_size=data.get('max_size', 10485760),
            backup_count=data.get('backup_count', 5)
        )
    
    @property
    def data_config(self) -> DataConfig:
        """数据存储配置"""
        data = self.get('data', {})
        return DataConfig(
            dir=data.get('dir', './data'),
            save_history=data.get('save_history', True)
        )
    
    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        
        # CapMonster 配置验证
        if not self.capmonster_api_key:
            errors.append("capmonster.api_key 未配置")
        
        # 通知配置验证
        notifications = self.notifications
        has_notification = (
            notifications.telegram.enabled or
            notifications.discord.enabled or
            notifications.email.enabled
        )
        
        if not has_notification:
            errors.append("至少需要启用一个通知渠道")
        
        if notifications.telegram.enabled:
            if not notifications.telegram.bot_token:
                errors.append("Telegram bot_token 未配置")
            if not notifications.telegram.chat_id:
                errors.append("Telegram chat_id 未配置")
        
        if notifications.discord.enabled:
            if not notifications.discord.webhook_url:
                errors.append("Discord webhook_url 未配置")
        
        if notifications.email.enabled:
            if not notifications.email.smtp_user:
                errors.append("Email smtp_user 未配置")
            if not notifications.email.to_addrs:
                errors.append("Email to_addrs 未配置")
            # 验证 SMTP 端口范围
            smtp_port = notifications.email.smtp_port
            if not (1 <= smtp_port <= 65535):
                errors.append(f"Email smtp_port 无效: {smtp_port}，应在 1-65535 范围内")
        
        # 产品配置验证
        products = self.products
        if not products:
            errors.append("未配置任何监控产品")
        else:
            for i, p in enumerate(products):
                if not p.name:
                    errors.append(f"产品 #{i+1}: name 不能为空")
                if not p.url:
                    errors.append(f"产品 #{i+1}: url 不能为空")
                if not p.site:
                    errors.append(f"产品 #{i+1}: site 不能为空")
        
        # 监控配置数值范围验证
        monitor = self.monitor
        
        if monitor.check_interval < 10:
            errors.append(f"monitor.check_interval 过小: {monitor.check_interval}，最小值为 10 秒")
        if monitor.check_interval > 86400:
            errors.append(f"monitor.check_interval 过大: {monitor.check_interval}，最大值为 86400 秒")
        
        if monitor.retry_interval < 5:
            errors.append(f"monitor.retry_interval 过小: {monitor.retry_interval}，最小值为 5 秒")
        
        if monitor.max_retries < 0:
            errors.append(f"monitor.max_retries 不能为负数: {monitor.max_retries}")
        if monitor.max_retries > 10:
            errors.append(f"monitor.max_retries 过大: {monitor.max_retries}，最大值为 10")
        
        if monitor.concurrent_checks < 1:
            errors.append(f"monitor.concurrent_checks 过小: {monitor.concurrent_checks}，最小值为 1")
        if monitor.concurrent_checks > 20:
            errors.append(f"monitor.concurrent_checks 过大: {monitor.concurrent_checks}，建议不超过 20")
        
        # 浏览器配置验证
        browser = self.browser
        if browser.timeout < 1000:
            errors.append(f"browser.timeout 过小: {browser.timeout}，最小值为 1000 毫秒")
        if browser.timeout > 120000:
            errors.append(f"browser.timeout 过大: {browser.timeout}，最大值为 120000 毫秒")
        
        return errors


# 全局配置实例
_config: Optional[ConfigManager] = None


def get_config(config_file: str = "config.yaml") -> ConfigManager:
    """获取配置管理器实例"""
    global _config
    if _config is None:
        _config = ConfigManager(config_file)
    return _config


def init_config(config_file: str = "config.yaml", watch: bool = True) -> ConfigManager:
    """
    初始化配置
    
    Args:
        config_file: 配置文件路径
        watch: 是否监听文件变更
    
    Returns:
        ConfigManager 实例
    """
    global _config
    _config = ConfigManager(config_file)
    
    if watch:
        _config.start_watching()
    
    return _config
