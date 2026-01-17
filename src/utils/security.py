"""
安全工具模块
提供常用的安全相关工具函数
"""
import hashlib
import hmac
import re
import secrets
import string
from typing import Optional, Tuple
from urllib.parse import urlparse

from ..constants import SecurityDefaults


def generate_secure_token(length: int = 32) -> str:
    """
    生成安全的随机 token
    
    Args:
        length: token 长度（默认 32）
        
    Returns:
        随机 token 字符串
    """
    return secrets.token_urlsafe(length)


def generate_api_key(length: int = 32) -> str:
    """
    生成 API Key
    
    Args:
        length: Key 长度（默认 32）
        
    Returns:
        API Key 字符串
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def constant_time_compare(val1: str, val2: str) -> bool:
    """
    时序安全的字符串比较
    
    Args:
        val1: 第一个字符串
        val2: 第二个字符串
        
    Returns:
        是否相等
    """
    if not val1 or not val2:
        return False
    return hmac.compare_digest(val1.encode('utf-8'), val2.encode('utf-8'))


def mask_sensitive(value: str, show_chars: int = 4, mask_char: str = '*') -> str:
    """
    脱敏敏感信息
    
    Args:
        value: 原始值
        show_chars: 显示的字符数
        mask_char: 脱敏字符
        
    Returns:
        脱敏后的字符串
        
    Examples:
        >>> mask_sensitive("sk-abcdefg12345")
        'sk-a****'
        >>> mask_sensitive("api_key_secret", show_chars=6)
        'api_ke****'
    """
    if not value:
        return ""
    if len(value) <= show_chars:
        return mask_char * len(value)
    return value[:show_chars] + mask_char * 4


def mask_url_credentials(url: str) -> str:
    """
    脱敏 URL 中的凭据
    
    Args:
        url: 原始 URL
        
    Returns:
        脱敏后的 URL
        
    Examples:
        >>> mask_url_credentials("https://user:password@example.com/path")
        'https://user:****@example.com/path'
    """
    if not url:
        return ""
    
    try:
        parsed = urlparse(url)
        if parsed.password:
            # 替换密码
            masked = url.replace(f":{parsed.password}@", ":****@")
            return masked
        return url
    except Exception:
        return url


def validate_url(url: str, allow_internal: bool = False) -> Tuple[bool, Optional[str]]:
    """
    验证 URL 是否安全
    
    Args:
        url: 要验证的 URL
        allow_internal: 是否允许内网地址
        
    Returns:
        (is_valid, error_message)
    """
    if not url:
        return False, "URL 不能为空"
    
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL 解析失败: {e}"
    
    # 检查协议
    if parsed.scheme not in SecurityDefaults.ALLOWED_URL_SCHEMES:
        return False, f"不允许的协议: {parsed.scheme}"
    
    # 检查主机名
    if not parsed.netloc:
        return False, "URL 缺少主机名"
    
    hostname = parsed.hostname or ""
    hostname_lower = hostname.lower()
    
    if not allow_internal:
        # 检查禁止的主机名
        if hostname_lower in SecurityDefaults.FORBIDDEN_HOSTNAMES:
            return False, f"禁止访问内网地址: {hostname}"
        
        # 检查禁止的 IP 前缀
        for prefix in SecurityDefaults.FORBIDDEN_IP_PREFIXES:
            if hostname.startswith(prefix):
                return False, f"禁止访问内网 IP: {hostname}"
    
    return True, None


def is_safe_path(path: str, base_dir: str = ".") -> bool:
    """
    检查路径是否安全（防止路径遍历攻击）
    
    Args:
        path: 要检查的路径
        base_dir: 基础目录
        
    Returns:
        是否安全
    """
    import os
    
    # 规范化路径
    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(os.path.join(base_dir, path))
    
    # 检查是否在基础目录内
    return abs_path.startswith(abs_base)


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    清理文件名，移除不安全字符
    
    Args:
        filename: 原始文件名
        max_length: 最大长度
        
    Returns:
        安全的文件名
    """
    if not filename:
        return "unnamed"
    
    # 移除危险字符
    unsafe_chars = r'[<>:"/\\|?*\x00-\x1f]'
    safe_name = re.sub(unsafe_chars, '_', filename)
    
    # 移除开头/结尾的点和空格
    safe_name = safe_name.strip('. ')
    
    # 限制长度
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length]
    
    return safe_name or "unnamed"


def hash_string(value: str, algorithm: str = "sha256") -> str:
    """
    对字符串进行哈希
    
    Args:
        value: 要哈希的字符串
        algorithm: 哈希算法（默认 sha256）
        
    Returns:
        哈希值（十六进制）
    """
    hasher = hashlib.new(algorithm)
    hasher.update(value.encode('utf-8'))
    return hasher.hexdigest()


def validate_email(email: str) -> bool:
    """
    验证邮箱格式
    
    Args:
        email: 邮箱地址
        
    Returns:
        是否有效
    """
    if not email:
        return False
    
    # 简单的邮箱正则
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_discord_id(id_str: str) -> bool:
    """
    验证 Discord ID 格式（Snowflake ID）
    
    Args:
        id_str: ID 字符串
        
    Returns:
        是否有效
    """
    if not id_str:
        return False
    return bool(re.match(r'^\d{17,20}$', str(id_str)))
