"""
API 数据模型 (Pydantic Schemas)
"""
from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field

# 导入版本常量
try:
    from ..constants import VERSION
except ImportError:
    VERSION = "1.0.0"


class ProductStatus(str, Enum):
    """产品状态"""
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"
    ERROR = "error"
    CHECKING = "checking"


# ==================== 产品相关 ====================

class ProductBase(BaseModel):
    """产品基础模型"""
    name: str = Field(..., description="产品名称")
    url: str = Field(..., description="产品链接")
    site: str = Field(..., description="站点标识")
    enabled: bool = Field(True, description="是否启用")
    description: str = Field("", description="产品描述")
    check_interval: Optional[int] = Field(None, description="自定义检查间隔(秒)")


class ProductCreate(ProductBase):
    """创建产品"""
    pass


class ProductUpdate(BaseModel):
    """更新产品"""
    name: Optional[str] = None
    url: Optional[str] = None
    site: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    check_interval: Optional[int] = None


class ProductResponse(ProductBase):
    """产品响应"""
    id: str = Field(..., description="产品ID")
    status: ProductStatus = Field(ProductStatus.UNKNOWN, description="当前状态")
    price: Optional[float] = Field(None, description="价格")
    last_checked: Optional[datetime] = Field(None, description="最后检查时间")
    last_in_stock: Optional[datetime] = Field(None, description="最后有货时间")
    check_count: int = Field(0, description="检查次数")
    
    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """产品列表响应"""
    total: int = Field(..., description="总数")
    items: List[ProductResponse] = Field(..., description="产品列表")


# ==================== 状态相关 ====================

class MonitorStatus(BaseModel):
    """监控状态"""
    running: bool = Field(..., description="是否运行中")
    start_time: Optional[datetime] = Field(None, description="启动时间")
    uptime_seconds: Optional[int] = Field(None, description="运行时长(秒)")
    total_checks: int = Field(0, description="总检查次数")
    successful_checks: int = Field(0, description="成功检查次数")
    failed_checks: int = Field(0, description="失败检查次数")
    last_check_time: Optional[datetime] = Field(None, description="最后检查时间")


class ProductCheckResult(BaseModel):
    """产品检查结果"""
    product_id: str
    product_name: str
    status: ProductStatus
    price: Optional[float] = None
    stock_text: Optional[str] = None
    checked_at: datetime
    duration_ms: int
    changed: bool = False


class SystemStatus(BaseModel):
    """系统状态"""
    version: str = Field(default=VERSION, description="系统版本")
    monitor: MonitorStatus = Field(..., description="监控状态")
    redis_connected: bool = Field(..., description="Redis 连接状态")
    browser_ready: bool = Field(..., description="浏览器就绪状态")
    config_file: str = Field(..., description="配置文件路径")
    products_count: int = Field(..., description="产品数量")
    enabled_products_count: int = Field(..., description="启用产品数量")


# ==================== WebSocket 消息 ====================

class WSMessageType(str, Enum):
    """WebSocket 消息类型"""
    STOCK_CHANGE = "stock_change"
    CHECK_RESULT = "check_result"
    SYSTEM_STATUS = "system_status"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class WSMessage(BaseModel):
    """WebSocket 消息"""
    type: WSMessageType
    data: dict
    timestamp: datetime = Field(default_factory=datetime.now)


# ==================== 通用响应 ====================

class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool = True
    message: str = ""


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    detail: Optional[str] = None
