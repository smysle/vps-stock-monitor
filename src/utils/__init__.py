"""
工具模块
提供日志、助手函数、安全工具等通用功能
"""
from .logger import setup_logger, get_logger, setup_colored_logger
from .helpers import (
    generate_hash,
    extract_price,
    extract_specs,
    normalize_url,
    format_duration,
    format_size,
    clean_text,
    parse_stock_status,
    get_domain,
)
from .affiliate import (
    AffiliateManager,
    AffiliateConfig,
    affiliate_manager,
    setup_affiliates,
    get_affiliate_url,
    AFFILIATE_PARAM_FORMATS,
)
from .security import (
    generate_secure_token,
    generate_api_key,
    constant_time_compare,
    mask_sensitive,
    mask_url_credentials,
    validate_url,
    is_safe_path,
    sanitize_filename,
    hash_string,
    validate_email,
    validate_discord_id,
)
from .retry import (
    retry_async,
    async_retry,
    RetryError,
    CircuitBreaker,
    CircuitBreakerError,
)

__all__ = [
    # Logger
    "setup_logger",
    "get_logger",
    "setup_colored_logger",
    
    # Helpers
    "generate_hash",
    "extract_price",
    "extract_specs",
    "normalize_url",
    "format_duration",
    "format_size",
    "clean_text",
    "parse_stock_status",
    "get_domain",
    
    # Affiliate
    "AffiliateManager",
    "AffiliateConfig",
    "affiliate_manager",
    "setup_affiliates",
    "get_affiliate_url",
    "AFFILIATE_PARAM_FORMATS",
    
    # Security
    "generate_secure_token",
    "generate_api_key",
    "constant_time_compare",
    "mask_sensitive",
    "mask_url_credentials",
    "validate_url",
    "is_safe_path",
    "sanitize_filename",
    "hash_string",
    "validate_email",
    "validate_discord_id",
    
    # Retry
    "retry_async",
    "async_retry",
    "RetryError",
    "CircuitBreaker",
    "CircuitBreakerError",
]
