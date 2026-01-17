"""
常量定义模块
集中管理项目中使用的所有常量
"""
from typing import Final

# ==============================================================================
# 版本信息
# ==============================================================================
__version__: Final[str] = "1.0.0"
VERSION: Final[str] = __version__

# ==============================================================================
# Redis 配置
# ==============================================================================
REDIS_KEY_PREFIX: Final[str] = "vps_monitor"


class RedisKeys:
    """Redis Key 常量"""
    
    PREFIX: Final[str] = REDIS_KEY_PREFIX
    
    # 产品相关
    PRODUCTS: Final[str] = f"{PREFIX}:products"
    PRODUCT_STATUS: Final[str] = f"{PREFIX}:product_status:{{product_id}}"
    PRODUCT_HISTORY: Final[str] = f"{PREFIX}:product_history:{{product_id}}"
    
    # 监控状态
    MONITOR_STATUS: Final[str] = f"{PREFIX}:status"
    STATS: Final[str] = f"{PREFIX}:stats"
    CHECK_HISTORY: Final[str] = f"{PREFIX}:check_history"
    
    # Pub/Sub 频道
    CHANNEL_STOCK_CHANGE: Final[str] = f"{PREFIX}:stock_change"
    CHANNEL_CHECK_RESULT: Final[str] = f"{PREFIX}:check_result"
    CHANNEL_COMMAND: Final[str] = f"{PREFIX}:command"
    CHANNEL_CHECK_PRODUCT: Final[str] = f"{PREFIX}:check_product"
    CHANNEL_ERROR: Final[str] = f"{PREFIX}:error"
    
    @classmethod
    def product_status(cls, product_id: str) -> str:
        """获取产品状态 key"""
        return cls.PRODUCT_STATUS.format(product_id=product_id)
    
    @classmethod
    def product_history(cls, product_id: str) -> str:
        """获取产品历史 key"""
        return cls.PRODUCT_HISTORY.format(product_id=product_id)


# ==============================================================================
# WebSocket 配置
# ==============================================================================
DEFAULT_WS_TIMEOUT: Final[float] = 30.0
DEFAULT_WS_HEARTBEAT_INTERVAL: Final[float] = 25.0
MAX_WS_CONNECTIONS: Final[int] = 100
MAX_WS_MESSAGE_SIZE: Final[int] = 65536  # 64KB


# ==============================================================================
# 历史记录限制
# ==============================================================================
DEFAULT_MAX_GLOBAL_HISTORY: Final[int] = 1000
DEFAULT_MAX_PRODUCT_HISTORY: Final[int] = 100


# ==============================================================================
# 缓存过期时间（秒）
# ==============================================================================
PRODUCT_STATUS_TTL: Final[int] = 30 * 24 * 3600  # 30 天
PRODUCT_HISTORY_TTL: Final[int] = 7 * 24 * 3600   # 7 天


# ==============================================================================
# HTTP 请求配置
# ==============================================================================
class HTTPDefaults:
    """HTTP 请求默认配置"""
    
    TIMEOUT: Final[int] = 30
    MAX_RETRIES: Final[int] = 3
    RETRY_DELAY: Final[float] = 2.0
    RETRY_MULTIPLIER: Final[float] = 2.0  # 指数退避倍数
    MAX_RETRY_DELAY: Final[float] = 60.0


# ==============================================================================
# 监控配置范围
# ==============================================================================
class MonitorLimits:
    """监控配置限制"""
    
    # 检查间隔（秒）
    MIN_CHECK_INTERVAL: Final[int] = 10
    MAX_CHECK_INTERVAL: Final[int] = 86400  # 24小时
    DEFAULT_CHECK_INTERVAL: Final[int] = 300  # 5分钟
    
    # 重试配置
    MIN_RETRY_INTERVAL: Final[int] = 5
    MAX_RETRIES: Final[int] = 10
    
    # 并发配置
    MIN_CONCURRENT_CHECKS: Final[int] = 1
    MAX_CONCURRENT_CHECKS: Final[int] = 20
    DEFAULT_CONCURRENT_CHECKS: Final[int] = 1


# ==============================================================================
# 浏览器配置范围
# ==============================================================================
class BrowserLimits:
    """浏览器配置限制"""
    
    MIN_TIMEOUT: Final[int] = 1000      # 1秒
    MAX_TIMEOUT: Final[int] = 120000    # 2分钟
    DEFAULT_TIMEOUT: Final[int] = 30000  # 30秒
    
    MIN_VIEWPORT_WIDTH: Final[int] = 320
    MAX_VIEWPORT_WIDTH: Final[int] = 3840
    MIN_VIEWPORT_HEIGHT: Final[int] = 240
    MAX_VIEWPORT_HEIGHT: Final[int] = 2160


# ==============================================================================
# 通知配置
# ==============================================================================
class NotificationLimits:
    """通知配置限制"""
    
    # 速率限制（每分钟最大通知数）
    MAX_NOTIFICATIONS_PER_MINUTE: Final[int] = 30
    
    # 消息长度限制
    MAX_TITLE_LENGTH: Final[int] = 256
    MAX_BODY_LENGTH: Final[int] = 4096
    
    # Telegram 限制
    TELEGRAM_MAX_MESSAGE_LENGTH: Final[int] = 4096
    TELEGRAM_MAX_CAPTION_LENGTH: Final[int] = 1024
    
    # Discord 限制
    DISCORD_MAX_EMBED_TITLE: Final[int] = 256
    DISCORD_MAX_EMBED_DESCRIPTION: Final[int] = 4096
    DISCORD_MAX_EMBED_FIELDS: Final[int] = 25


# ==============================================================================
# SMTP 端口
# ==============================================================================
class SMTPPorts:
    """常见 SMTP 端口"""
    
    SMTP: Final[int] = 25
    SMTP_SUBMISSION: Final[int] = 587
    SMTPS: Final[int] = 465


# ==============================================================================
# 用户代理
# ==============================================================================
DEFAULT_USER_AGENTS: Final[list] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


# ==============================================================================
# 安全相关
# ==============================================================================
class SecurityDefaults:
    """安全相关默认值"""
    
    # API Key 最小长度
    MIN_API_KEY_LENGTH: Final[int] = 16
    RECOMMENDED_API_KEY_LENGTH: Final[int] = 32
    
    # 允许的 URL 协议
    ALLOWED_URL_SCHEMES: Final[tuple] = ("http", "https")
    
    # 禁止的内网 IP 前缀
    FORBIDDEN_IP_PREFIXES: Final[tuple] = (
        "127.",
        "10.",
        "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        "192.168.",
        "0.",
        "169.254.",  # Link-local
    )
    
    # 禁止的主机名
    FORBIDDEN_HOSTNAMES: Final[tuple] = (
        "localhost",
        "localhost.localdomain",
        "local",
    )


# ==============================================================================
# 文件路径
# ==============================================================================
class DefaultPaths:
    """默认文件路径"""
    
    CONFIG_FILE: Final[str] = "config.yaml"
    CONFIG_EXAMPLE: Final[str] = "config.yaml.example"
    ENV_FILE: Final[str] = ".env"
    ENV_EXAMPLE: Final[str] = ".env.example"
    
    LOG_DIR: Final[str] = "logs"
    DATA_DIR: Final[str] = "data"
    SCREENSHOTS_DIR: Final[str] = "screenshots"


# ==============================================================================
# 日志级别
# ==============================================================================
VALID_LOG_LEVELS: Final[tuple] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
