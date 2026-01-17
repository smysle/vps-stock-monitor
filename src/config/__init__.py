"""
配置模块
"""
from .settings import (
    ConfigManager,
    SiteConfig,
    TelegramConfig,
    DiscordConfig,
    EmailConfig,
    NotificationConfig,
    MonitorConfig,
    BrowserConfig,
    ProxyConfig,
    LoggingConfig,
    DataConfig,
    ProductConfig,
    get_config,
    init_config,
    DEFAULT_SITE_CONFIGS,
)
from .products import (
    Product,
    ProductStatus,
    StockStatus,
    Site,
    PRODUCTS,
    get_enabled_products,
    get_products_by_site,
    add_custom_product,
)

__all__ = [
    # Settings
    "ConfigManager",
    "SiteConfig",
    "TelegramConfig",
    "DiscordConfig",
    "EmailConfig",
    "NotificationConfig",
    "MonitorConfig",
    "BrowserConfig",
    "ProxyConfig",
    "LoggingConfig",
    "DataConfig",
    "ProductConfig",
    "get_config",
    "init_config",
    "DEFAULT_SITE_CONFIGS",
    # Products
    "Product",
    "ProductStatus",
    "StockStatus",
    "Site",
    "PRODUCTS",
    "get_enabled_products",
    "get_products_by_site",
    "add_custom_product",
]
