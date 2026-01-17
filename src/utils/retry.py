"""
重试工具模块
提供统一的重试机制
"""
import asyncio
import functools
import logging
from typing import Callable, Optional, Type, Tuple, Union, Any

from ..constants import HTTPDefaults


logger = logging.getLogger(__name__)


class RetryError(Exception):
    """重试失败异常"""
    
    def __init__(
        self, 
        message: str, 
        attempts: int = 0, 
        last_exception: Optional[Exception] = None
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception


async def retry_async(
    func: Callable,
    max_retries: int = HTTPDefaults.MAX_RETRIES,
    delay: float = HTTPDefaults.RETRY_DELAY,
    multiplier: float = HTTPDefaults.RETRY_MULTIPLIER,
    max_delay: float = HTTPDefaults.MAX_RETRY_DELAY,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    *args,
    **kwargs
) -> Any:
    """
    异步重试执行函数
    
    Args:
        func: 要执行的异步函数
        max_retries: 最大重试次数
        delay: 初始延迟（秒）
        multiplier: 延迟倍数（指数退避）
        max_delay: 最大延迟
        exceptions: 要捕获的异常类型
        on_retry: 重试时的回调函数
        *args, **kwargs: 传递给 func 的参数
        
    Returns:
        func 的返回值
        
    Raises:
        RetryError: 重试次数用尽后抛出
    """
    last_exception = None
    current_delay = delay
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
            
        except exceptions as e:
            last_exception = e
            
            if attempt >= max_retries:
                break
            
            # 调用重试回调
            if on_retry:
                try:
                    on_retry(attempt + 1, e)
                except Exception:
                    pass
            
            logger.warning(
                f"操作失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}, "
                f"将在 {current_delay:.1f}s 后重试"
            )
            
            await asyncio.sleep(current_delay)
            
            # 计算下次延迟（指数退避）
            current_delay = min(current_delay * multiplier, max_delay)
    
    raise RetryError(
        f"操作失败，已重试 {max_retries} 次",
        attempts=max_retries + 1,
        last_exception=last_exception
    )


def async_retry(
    max_retries: int = HTTPDefaults.MAX_RETRIES,
    delay: float = HTTPDefaults.RETRY_DELAY,
    multiplier: float = HTTPDefaults.RETRY_MULTIPLIER,
    max_delay: float = HTTPDefaults.MAX_RETRY_DELAY,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """
    异步重试装饰器
    
    Usage:
        @async_retry(max_retries=3, exceptions=(aiohttp.ClientError,))
        async def fetch_data():
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(
                func,
                max_retries=max_retries,
                delay=delay,
                multiplier=multiplier,
                max_delay=max_delay,
                exceptions=exceptions,
                on_retry=on_retry,
                *args,
                **kwargs
            )
        return wrapper
    return decorator


class CircuitBreaker:
    """
    断路器模式实现
    
    当连续失败达到阈值时，自动进入"断开"状态，
    拒绝新请求一段时间后进入"半开"状态尝试恢复。
    
    Usage:
        breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)
        
        async def call_api():
            async with breaker:
                return await do_request()
    """
    
    STATE_CLOSED = "closed"      # 正常状态
    STATE_OPEN = "open"          # 断开状态（拒绝请求）
    STATE_HALF_OPEN = "half_open"  # 半开状态（尝试恢复）
    
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        half_open_max_calls: int = 1
    ):
        """
        初始化断路器
        
        Args:
            failure_threshold: 连续失败次数阈值
            reset_timeout: 断开后重试的超时时间（秒）
            half_open_max_calls: 半开状态允许的最大调用次数
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self._state = self.STATE_CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> str:
        return self._state
    
    @property
    def is_closed(self) -> bool:
        return self._state == self.STATE_CLOSED
    
    @property
    def is_open(self) -> bool:
        return self._state == self.STATE_OPEN
    
    async def __aenter__(self):
        await self._before_call()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self._on_success()
        else:
            await self._on_failure()
        return False
    
    async def _before_call(self):
        """调用前检查"""
        async with self._lock:
            if self._state == self.STATE_OPEN:
                # 检查是否应该进入半开状态
                if self._last_failure_time:
                    elapsed = asyncio.get_event_loop().time() - self._last_failure_time
                    if elapsed >= self.reset_timeout:
                        self._state = self.STATE_HALF_OPEN
                        self._success_count = 0
                        logger.info("断路器进入半开状态")
                    else:
                        raise CircuitBreakerError(
                            f"断路器处于断开状态，请等待 {self.reset_timeout - elapsed:.1f}s"
                        )
    
    async def _on_success(self):
        """调用成功"""
        async with self._lock:
            self._failure_count = 0
            
            if self._state == self.STATE_HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._state = self.STATE_CLOSED
                    logger.info("断路器已恢复正常状态")
    
    async def _on_failure(self):
        """调用失败"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = asyncio.get_event_loop().time()
            
            if self._state == self.STATE_HALF_OPEN:
                # 半开状态下失败，立即断开
                self._state = self.STATE_OPEN
                logger.warning("断路器半开状态失败，重新断开")
            elif self._failure_count >= self.failure_threshold:
                # 达到阈值，断开
                self._state = self.STATE_OPEN
                logger.warning(
                    f"断路器已断开（连续失败 {self._failure_count} 次）"
                )
    
    def reset(self):
        """手动重置断路器"""
        self._state = self.STATE_CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class CircuitBreakerError(Exception):
    """断路器错误"""
    pass
