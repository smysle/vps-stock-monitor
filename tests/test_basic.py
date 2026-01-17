"""
基础测试 - 验证项目结构和导入
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """测试所有模块是否可以正确导入"""
    # 配置模块
    from src.config import Settings, Product, ProductStatus, StockStatus
    from src.config.products import PRODUCTS, get_enabled_products
    
    # 核心模块
    from src.core import BrowserManager, VPSMonitor, MonitorScheduler
    
    # 验证码模块
    from src.captcha import CapMonsterClient, CaptchaSolver
    
    # 通知模块
    from src.notifications import TelegramNotifier, DiscordNotifier
    from src.notifications.base import NotificationManager, NotificationMessage
    
    # 工具模块
    from src.utils import setup_logger, extract_price
    
    assert True


def test_settings_from_env():
    """测试从环境变量加载配置"""
    import os
    
    # 设置测试环境变量
    os.environ["CAPMONSTER_API_KEY"] = "test_key"
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
    os.environ["TELEGRAM_CHAT_ID"] = "123456"
    
    from src.config import Settings
    
    settings = Settings.from_env()
    
    assert settings.capmonster_api_key == "test_key"
    assert settings.telegram_bot_token == "test_token"
    assert settings.telegram_chat_id == "123456"
    
    # 清理
    del os.environ["CAPMONSTER_API_KEY"]
    del os.environ["TELEGRAM_BOT_TOKEN"]
    del os.environ["TELEGRAM_CHAT_ID"]


def test_products():
    """测试产品配置"""
    from src.config.products import PRODUCTS, get_enabled_products, Product
    
    # 验证产品列表不为空
    assert len(PRODUCTS) > 0
    
    # 验证产品结构
    for product in PRODUCTS:
        assert isinstance(product, Product)
        assert product.name
        assert product.url
        assert product.site
    
    # 验证获取启用的产品
    enabled = get_enabled_products()
    assert all(p.enabled for p in enabled)


def test_product_status():
    """测试产品状态枚举"""
    from src.config.products import ProductStatus
    
    assert ProductStatus.IN_STOCK.value == "in_stock"
    assert ProductStatus.OUT_OF_STOCK.value == "out_of_stock"
    assert ProductStatus.ERROR.value == "error"


def test_stock_status():
    """测试库存状态"""
    from src.config.products import Product, ProductStatus, StockStatus
    
    product = Product(
        name="Test Product",
        url="https://example.com",
        site="example.com",
        description="Test"
    )
    
    # 测试有货状态
    status_in_stock = StockStatus(
        product=product,
        status=ProductStatus.IN_STOCK,
        price=9.99
    )
    assert status_in_stock.in_stock == True
    
    # 测试缺货状态
    status_out = StockStatus(
        product=product,
        status=ProductStatus.OUT_OF_STOCK
    )
    assert status_out.in_stock == False


def test_extract_price():
    """测试价格提取"""
    from src.utils.helpers import extract_price
    
    assert extract_price("$19.99") == 19.99
    assert extract_price("Price: $49.99 USD") == 49.99
    assert extract_price("¥99.00") == 99.00
    assert extract_price("€29.99") == 29.99


def test_site_config():
    """测试站点配置"""
    from src.config import Settings
    
    settings = Settings.from_env()
    
    # 测试获取已知站点配置
    bwg_config = settings.get_site_config("bandwagonhost.com")
    assert bwg_config.out_of_stock_text == "Out of Stock"
    
    # 测试获取未知站点配置（应返回默认配置）
    unknown_config = settings.get_site_config("unknown-site.com")
    assert unknown_config.stock_selector is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
