"""
通用辅助函数
"""
import re
import hashlib
import asyncio
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin


def generate_hash(content: str) -> str:
    """生成内容哈希值"""
    return hashlib.md5(content.encode()).hexdigest()


def extract_price(text: str) -> Optional[float]:
    """
    从文本中提取价格
    
    Args:
        text: 包含价格的文本
        
    Returns:
        提取的价格（浮点数）或 None
    """
    # 匹配各种价格格式: $19.99, 19.99 USD, ¥99.00 等
    patterns = [
        r'\$\s*([\d,]+\.?\d*)',           # $19.99
        r'([\d,]+\.?\d*)\s*(?:USD|usd)',  # 19.99 USD
        r'¥\s*([\d,]+\.?\d*)',            # ¥99.00
        r'€\s*([\d,]+\.?\d*)',            # €19.99
        r'([\d,]+\.?\d*)\s*(?:EUR|eur)',  # 19.99 EUR
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                return float(price_str)
            except ValueError:
                continue
    
    return None


def extract_specs(text: str) -> Dict[str, Any]:
    """
    从文本中提取 VPS 规格
    
    Args:
        text: 包含规格的文本
        
    Returns:
        规格字典
    """
    specs = {}
    
    # CPU 核心数
    cpu_patterns = [
        r'(\d+)\s*(?:v?CPU|核|Core)',
        r'(\d+)\s*x\s*(?:CPU|Core)',
    ]
    for pattern in cpu_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            specs['cpu'] = int(match.group(1))
            break
    
    # 内存
    ram_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:GB|G)\s*(?:RAM|内存|Memory)',
        r'(?:RAM|内存|Memory)[:\s]*(\d+(?:\.\d+)?)\s*(?:GB|G)',
        r'(\d+)\s*MB\s*(?:RAM|内存|Memory)',
    ]
    for pattern in ram_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if 'MB' in pattern:
                value = value / 1024
            specs['ram_gb'] = value
            break
    
    # 存储
    storage_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:GB|G)\s*(?:SSD|NVMe|HDD|Storage|硬盘|存储)',
        r'(?:SSD|NVMe|HDD|Storage|硬盘|存储)[:\s]*(\d+(?:\.\d+)?)\s*(?:GB|G)',
        r'(\d+(?:\.\d+)?)\s*(?:TB|T)\s*(?:SSD|NVMe|HDD|Storage|硬盘|存储)',
    ]
    for pattern in storage_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if 'TB' in pattern or 'T' in pattern:
                value = value * 1024
            specs['storage_gb'] = value
            break
    
    # 带宽/流量
    bandwidth_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:TB|T)\s*(?:Bandwidth|Traffic|流量|带宽)',
        r'(?:Bandwidth|Traffic|流量|带宽)[:\s]*(\d+(?:\.\d+)?)\s*(?:TB|T)',
        r'(\d+(?:\.\d+)?)\s*(?:GB|G)\s*(?:Bandwidth|Traffic|流量|带宽)',
    ]
    for pattern in bandwidth_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            if 'GB' in pattern or 'G' in pattern:
                value = value / 1024
            specs['bandwidth_tb'] = value
            break
    
    return specs


def normalize_url(url: str, base_url: Optional[str] = None) -> str:
    """
    规范化 URL
    
    Args:
        url: 原始 URL
        base_url: 基础 URL（用于相对路径）
        
    Returns:
        规范化后的 URL
    """
    if base_url:
        url = urljoin(base_url, url)
    
    parsed = urlparse(url)
    
    # 确保有协议
    if not parsed.scheme:
        url = f"https://{url}"
    
    return url


def format_duration(seconds: float) -> str:
    """
    格式化时间间隔
    
    Args:
        seconds: 秒数
        
    Returns:
        格式化的时间字符串
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}小时"
    else:
        days = seconds / 86400
        return f"{days:.1f}天"


def format_size(bytes_size: int) -> str:
    """
    格式化文件大小
    
    Args:
        bytes_size: 字节数
        
    Returns:
        格式化的大小字符串
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} PB"


def retry_async(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    异步重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 初始延迟（秒）
        backoff: 延迟倍数
        exceptions: 需要重试的异常类型
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            
            raise last_exception
        
        return wrapper
    return decorator


def clean_text(text: str) -> str:
    """
    清理文本（去除多余空白字符）
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    # 替换多个空白字符为单个空格
    text = re.sub(r'\s+', ' ', text)
    # 去除首尾空白
    text = text.strip()
    return text


def parse_stock_status(text: str) -> bool:
    """
    解析库存状态
    
    Args:
        text: 包含库存状态的文本
        
    Returns:
        True 表示有货，False 表示缺货
    """
    text_lower = text.lower()
    
    # 缺货关键词
    out_of_stock_keywords = [
        'out of stock', 'sold out', 'unavailable', 'not available',
        '缺货', '售罄', '无货', '暂无库存', '已售完',
        'coming soon', 'notify me', 'waitlist',
    ]
    
    for keyword in out_of_stock_keywords:
        if keyword in text_lower:
            return False
    
    # 有货关键词
    in_stock_keywords = [
        'in stock', 'available', 'add to cart', 'buy now', 'order now',
        '有货', '现货', '立即购买', '加入购物车', '立即订购',
    ]
    
    for keyword in in_stock_keywords:
        if keyword in text_lower:
            return True
    
    # 默认返回 False（保守策略）
    return False


def get_domain(url: str) -> str:
    """
    从 URL 中提取域名
    
    Args:
        url: 完整 URL
        
    Returns:
        域名
    """
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split('/')[0]


def mask_sensitive(text: str, visible_chars: int = 4) -> str:
    """
    遮蔽敏感信息
    
    Args:
        text: 原始文本
        visible_chars: 可见字符数
        
    Returns:
        遮蔽后的文本
    """
    if len(text) <= visible_chars * 2:
        return '*' * len(text)
    
    return text[:visible_chars] + '*' * (len(text) - visible_chars * 2) + text[-visible_chars:]
