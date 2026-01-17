"""
产品配置模块
定义要监控的 VPS 产品列表
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime


class Site(str, Enum):
    """支持的站点"""
    BANDWAGONHOST = "bandwagonhost"
    DMIT = "dmit"
    RACKNERD = "racknerd"
    HOSTDARE = "hostdare"
    GREENCLOUD = "greencloud"
    CLOUDCONE = "cloudcone"
    CUSTOM = "custom"


class ProductStatus(Enum):
    """产品状态"""
    UNKNOWN = "unknown"
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    ERROR = "error"


@dataclass
class StockStatus:
    """库存状态"""
    product: 'Product'
    status: ProductStatus
    price: Optional[float] = None
    stock_text: Optional[str] = None
    error_message: Optional[str] = None
    checked_at: Optional[str] = None
    
    @property
    def in_stock(self) -> bool:
        """是否有货"""
        return self.status == ProductStatus.IN_STOCK


@dataclass
class Product:
    """产品配置"""
    name: str
    url: str
    site: str
    description: str = ""
    enabled: bool = True
    check_interval: Optional[int] = None  # 覆盖全局间隔
    
    # 选择器配置（可选，用于自定义解析）
    stock_selector: Optional[str] = None
    price_selector: Optional[str] = None
    out_of_stock_text: list[str] = field(default_factory=list)
    in_stock_text: list[str] = field(default_factory=list)
    
    # 通知配置
    notify_on_restock: bool = True
    notify_on_price_change: bool = False
    
    def __post_init__(self):
        if not self.out_of_stock_text:
            self.out_of_stock_text = [
                "out of stock",
                "sold out",
                "unavailable",
                "缺货",
                "已售罄"
            ]


# 预定义产品列表
PRODUCTS: list[Product] = [
    # ==================== 搬瓦工 ====================
    Product(
        name="搬瓦工 CN2 GIA-E 20G",
        url="https://bandwagonhost.com/cart.php?a=add&pid=87",
        site=Site.BANDWAGONHOST,
        description="CN2 GIA-E 限量版，1核/1G/20G SSD/1T流量",
        enabled=True,
    ),
    Product(
        name="搬瓦工 CN2 GIA-E 40G",
        url="https://bandwagonhost.com/cart.php?a=add&pid=88",
        site=Site.BANDWAGONHOST,
        description="CN2 GIA-E 限量版，2核/2G/40G SSD/2T流量",
        enabled=True,
    ),
    Product(
        name="搬瓦工 THE PLAN V2",
        url="https://bandwagonhost.com/cart.php?a=add&pid=144",
        site=Site.BANDWAGONHOST,
        description="THE PLAN V2 限量版",
        enabled=True,
    ),
    
    # ==================== DMIT ====================
    Product(
        name="DMIT LAX Pro Mini",
        url="https://www.dmit.io/cart.php?a=add&pid=183",
        site=Site.DMIT,
        description="洛杉矶 CN2 GIA，1核/1G/10G SSD/800G流量",
        enabled=True,
    ),
    Product(
        name="DMIT LAX Pro Micro",
        url="https://www.dmit.io/cart.php?a=add&pid=184",
        site=Site.DMIT,
        description="洛杉矶 CN2 GIA，1核/2G/20G SSD/1.2T流量",
        enabled=True,
    ),
    Product(
        name="DMIT HKG Pro Mini",
        url="https://www.dmit.io/cart.php?a=add&pid=189",
        site=Site.DMIT,
        description="香港 CN2 GIA，1核/1G/10G SSD/400G流量",
        enabled=True,
    ),
    
    # ==================== RackNerd ====================
    Product(
        name="RackNerd 768MB KVM",
        url="https://my.racknerd.com/cart.php?a=add&pid=695",
        site=Site.RACKNERD,
        description="768MB RAM / 15GB SSD / 1TB 流量",
        enabled=False,  # 示例：禁用
    ),
    Product(
        name="RackNerd 1GB KVM",
        url="https://my.racknerd.com/cart.php?a=add&pid=696",
        site=Site.RACKNERD,
        description="1GB RAM / 20GB SSD / 2TB 流量",
        enabled=False,
    ),
    
    # ==================== HostDare ====================
    Product(
        name="HostDare CSSD1",
        url="https://manage.hostdare.com/cart.php?a=add&pid=112",
        site=Site.HOSTDARE,
        description="CN2 GIA，1核/756M/35G SSD/600G流量",
        enabled=True,
    ),
    Product(
        name="HostDare CSSD2",
        url="https://manage.hostdare.com/cart.php?a=add&pid=113",
        site=Site.HOSTDARE,
        description="CN2 GIA，2核/1G/65G SSD/1T流量",
        enabled=True,
    ),
    
    # ==================== GreenCloud ====================
    Product(
        name="GreenCloud Budget KVM",
        url="https://greencloudvps.com/billing/cart.php?a=add&pid=318",
        site=Site.GREENCLOUD,
        description="Budget KVM VPS",
        enabled=False,
    ),
    
    # ==================== CloudCone ====================
    Product(
        name="CloudCone SC2 VPS",
        url="https://app.cloudcone.com/compute/create",
        site=Site.CLOUDCONE,
        description="CloudCone 特价 VPS",
        enabled=False,
    ),
]


def get_enabled_products() -> list[Product]:
    """获取启用的产品列表"""
    return [p for p in PRODUCTS if p.enabled]


def get_products_by_site(site: str) -> list[Product]:
    """按站点获取产品"""
    return [p for p in PRODUCTS if p.site == site and p.enabled]


def add_custom_product(
    name: str,
    url: str,
    description: str = "",
    stock_selector: Optional[str] = None,
    price_selector: Optional[str] = None,
) -> Product:
    """添加自定义产品"""
    product = Product(
        name=name,
        url=url,
        site=Site.CUSTOM,
        description=description,
        stock_selector=stock_selector,
        price_selector=price_selector,
    )
    PRODUCTS.append(product)
    return product
