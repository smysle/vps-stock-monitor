#!/usr/bin/env python3
"""
VPS 补货监控系统 - 主程序入口
支持 YAML 配置文件和热重载
支持 CapMonster Cloud 自动打码过 Cloudflare 验证
支持 FastAPI 管理面板 + Redis 状态存储
"""
import os
import sys
import asyncio
import signal
import argparse
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config.settings import (
    ConfigManager, init_config, get_config,
    ProductConfig
)
from src.config.products import Product, get_enabled_products
from src.core.browser import BrowserManager
from src.core.monitor import VPSMonitor
from src.core.scheduler import MonitorScheduler
from src.captcha.capmonster import CapMonsterClient
from src.notifications.base import NotificationManager
from src.notifications.telegram import TelegramNotifier
from src.notifications.discord import DiscordNotifier
from src.utils.logger import setup_logger, setup_colored_logger
from src.utils.affiliate import setup_affiliates


# 全局变量
scheduler: Optional[MonitorScheduler] = None
browser: Optional[BrowserManager] = None
capmonster: Optional[CapMonsterClient] = None
config: Optional[ConfigManager] = None


def product_config_to_product(pc: ProductConfig) -> Product:
    """将 ProductConfig 转换为 Product"""
    return Product(
        name=pc.name,
        url=pc.url,
        site=pc.site,
        description=pc.description,
        enabled=pc.enabled,
        check_interval=pc.check_interval,
        stock_selector=pc.stock_selector,
        price_selector=pc.price_selector,
        out_of_stock_text=pc.out_of_stock_text,
        in_stock_text=pc.in_stock_text,
        notify_on_restock=pc.notify_on_restock,
        notify_on_price_change=pc.notify_on_price_change
    )


async def setup_notifications(config: ConfigManager) -> NotificationManager:
    """设置通知管理器"""
    manager = NotificationManager()
    notifications = config.notifications
    
    # Telegram 通知
    if notifications.telegram.enabled:
        telegram = TelegramNotifier(
            bot_token=notifications.telegram.bot_token,
            chat_id=notifications.telegram.chat_id,
            parse_mode=notifications.telegram.parse_mode,
            disable_preview=notifications.telegram.disable_preview
        )
        if await telegram.test():
            manager.add_provider(telegram)
            print("✅ Telegram 通知已启用")
        else:
            print("❌ Telegram 连接失败")
    
    # Discord 通知
    if notifications.discord.enabled:
        discord = DiscordNotifier(
            webhook_url=notifications.discord.webhook_url
        )
        manager.add_provider(discord)
        print("✅ Discord 通知已启用")
    
    return manager


def on_config_change(cfg: ConfigManager):
    """配置变更回调"""
    print("\n🔄 配置已更新!")
    
    # 更新 Affiliate 配置
    affiliates = cfg.affiliates
    if affiliates:
        setup_affiliates(affiliates)
        print(f"   📎 Affiliate 配置已更新: {len(affiliates)} 个站点")
    
    # 更新产品列表
    products = cfg.products
    enabled_count = sum(1 for p in products if p.enabled)
    print(f"   📦 产品列表已更新: {enabled_count}/{len(products)} 个启用")
    
    # 更新监控间隔
    monitor_config = cfg.monitor
    print(f"   ⏱️ 检查间隔: {monitor_config.check_interval} 秒")
    
    print()


async def main_loop(cfg: ConfigManager):
    """主监控循环"""
    global scheduler, browser, capmonster
    
    logger = setup_colored_logger("vps-monitor")
    
    print("\n" + "=" * 60)
    print("🚀 VPS 补货监控系统启动")
    print("=" * 60)
    
    # 验证配置
    errors = cfg.validate()
    if errors:
        for error in errors:
            print(f"❌ 配置错误: {error}")
        return
    
    # 设置 Affiliate 配置
    affiliates = cfg.affiliates
    if affiliates:
        setup_affiliates(affiliates)
        print(f"✅ Affiliate 推广已配置: {len(affiliates)} 个站点")
    
    # 初始化 CapMonster 客户端
    api_key = cfg.capmonster_api_key
    if api_key:
        capmonster = CapMonsterClient(api_key)
        try:
            balance = await capmonster.get_balance()
            print(f"✅ CapMonster Cloud 已连接，余额: ${balance:.2f}")
        except Exception as e:
            print(f"⚠️ CapMonster Cloud 连接失败: {e}")
            capmonster = None
    
    # 初始化浏览器
    browser_config = cfg.browser
    proxy_config = cfg.proxy
    browser = BrowserManager(
        headless=browser_config.headless,
        timeout=browser_config.timeout,
        proxy=proxy_config.url if proxy_config.enabled else None,
        user_agent=browser_config.user_agent or None
    )
    await browser.initialize()
    print("✅ 浏览器已启动")
    
    # 设置通知
    notification_manager = await setup_notifications(cfg)
    
    # 创建监控器
    monitor = VPSMonitor(
        browser=browser,
        capmonster=capmonster,
        notification_manager=notification_manager,
        config=cfg
    )
    
    # 设置监控器到 API 依赖中
    try:
        from src.api.deps import set_monitor
        set_monitor(monitor)
    except ImportError:
        pass
    
    # 获取产品列表
    products_config = cfg.products
    products = [
        product_config_to_product(pc) 
        for pc in products_config 
        if pc.enabled
    ]
    
    # 如果 YAML 中没有产品，从 products.py 获取
    if not products:
        products = get_enabled_products()
    
    if not products:
        print("❌ 没有配置监控产品")
        return
    
    # 创建调度器
    monitor_config = cfg.monitor
    scheduler = MonitorScheduler(
        monitor=monitor,
        products=products,
        check_interval=monitor_config.check_interval,
        retry_interval=monitor_config.retry_interval,
        max_retries=monitor_config.max_retries,
        config=cfg
    )
    
    # 注册配置变更回调
    cfg.on_config_change(on_config_change)
    
    # 添加结果回调
    def on_result(result):
        status_icon = "✅" if result.status.in_stock else "❌"
        change_icon = "🔔" if result.changed else ""
        logger.info(
            f"{status_icon} {result.product.name} - "
            f"{'有货' if result.status.in_stock else '缺货'} "
            f"{change_icon} ({result.duration_ms}ms)"
        )
    
    scheduler.add_callback(on_result)
    
    print(f"\n📦 监控产品数量: {len(products)}")
    print(f"⏱️ 检查间隔: {monitor_config.check_interval} 秒")
    print("📝 配置文件支持热重载，修改后自动生效")
    print("\n" + "-" * 60)
    
    # 启动调度器
    await scheduler.start()
    
    # 等待停止信号
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


async def run_once(cfg: ConfigManager):
    """执行一次检查"""
    global browser, capmonster
    
    logger = setup_colored_logger("vps-monitor")
    
    print("\n🔍 执行单次检查...")
    
    # 设置 Affiliate 配置
    affiliates = cfg.affiliates
    if affiliates:
        setup_affiliates(affiliates)
    
    # 初始化 CapMonster 客户端
    api_key = cfg.capmonster_api_key
    if api_key:
        capmonster = CapMonsterClient(api_key)
    
    # 初始化浏览器
    browser_config = cfg.browser
    proxy_config = cfg.proxy
    browser = BrowserManager(
        headless=browser_config.headless,
        timeout=browser_config.timeout,
        proxy=proxy_config.url if proxy_config.enabled else None
    )
    await browser.initialize()
    
    # 设置通知
    notification_manager = await setup_notifications(cfg)
    
    # 创建监控器
    monitor = VPSMonitor(
        browser=browser,
        capmonster=capmonster,
        notification_manager=notification_manager,
        config=cfg
    )
    
    # 获取产品列表
    products_config = cfg.products
    products = [
        product_config_to_product(pc) 
        for pc in products_config 
        if pc.enabled
    ]
    
    if not products:
        products = get_enabled_products()
    
    if not products:
        print("❌ 没有配置监控产品")
        return
    
    # 执行检查
    results = await monitor.check_products(products)
    
    print("\n" + "=" * 60)
    print("📊 检查结果")
    print("=" * 60)
    
    for result in results:
        status_icon = "✅" if result.status.in_stock else "❌"
        print(f"{status_icon} {result.product.name}")
        if result.status.price:
            print(f"   💰 价格: ${result.status.price:.2f}")
        if result.status.stock_text:
            print(f"   📝 状态: {result.status.stock_text[:50]}")
        if result.status.error_message:
            print(f"   ⚠️ 错误: {result.status.error_message}")
        print()
    
    # 统计
    in_stock = sum(1 for r in results if r.status.in_stock)
    print(f"📈 统计: {in_stock}/{len(results)} 有货")
    
    # 清理
    await browser.close()
    if capmonster:
        await capmonster.close()


async def shutdown():
    """关闭程序"""
    global scheduler, browser, capmonster, config, _shutdown_event
    
    print("\n🛑 正在关闭...")
    
    if config:
        config.stop_watching()
    
    if scheduler:
        await scheduler.stop()
    
    if browser:
        await browser.close()
    
    if capmonster:
        await capmonster.close()
    
    print("👋 已退出")


# 用于优雅关闭的事件
_shutdown_event: Optional[asyncio.Event] = None


def create_shutdown_handler(loop: asyncio.AbstractEventLoop):
    """创建信号处理器"""
    def handler():
        global _shutdown_event
        if _shutdown_event:
            _shutdown_event.set()
    return handler


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="VPS 补货监控系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                    # 启动监控
  python main.py --once             # 执行一次检查
  python main.py -c my-config.yaml  # 使用自定义配置文件
  python main.py --no-watch         # 禁用配置热重载
        """
    )
    
    parser.add_argument(
        "--once", "-o",
        action="store_true",
        help="只执行一次检查"
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    
    parser.add_argument(
        "--no-watch",
        action="store_true",
        help="禁用配置文件热重载"
    )
    
    parser.add_argument(
        "--validate",
        action="store_true",
        help="验证配置文件并退出"
    )
    
    parser.add_argument(
        "--api",
        action="store_true",
        help="启动 FastAPI 管理接口"
    )
    
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="只启动 FastAPI 管理接口（不启动监控）"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="API 服务器监听地址 (默认: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API 服务器监听端口 (默认: 8000)"
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    global config
    
    args = parse_args()
    
    # 初始化配置
    watch = not args.no_watch and not args.once
    config = init_config(args.config, watch=watch)
    
    # 验证模式
    if args.validate:
        print(f"📄 验证配置文件: {args.config}")
        errors = config.validate()
        if errors:
            print("\n❌ 配置验证失败:")
            for error in errors:
                print(f"   - {error}")
            sys.exit(1)
        else:
            print("\n✅ 配置验证通过!")
            
            # 显示配置摘要
            print("\n📋 配置摘要:")
            print(f"   - CapMonster API Key: {'已配置' if config.capmonster_api_key else '未配置'}")
            
            notifications = config.notifications
            print(f"   - Telegram: {'启用' if notifications.telegram.enabled else '禁用'}")
            print(f"   - Discord: {'启用' if notifications.discord.enabled else '禁用'}")
            print(f"   - Email: {'启用' if notifications.email.enabled else '禁用'}")
            
            products = config.products
            enabled = sum(1 for p in products if p.enabled)
            print(f"   - 产品数量: {enabled}/{len(products)} 启用")
            
            affiliates = config.affiliates
            print(f"   - Affiliate: {len(affiliates)} 个站点")
            
            sys.exit(0)
    
    # 只启动 API 模式
    if args.api_only:
        run_api_server(args.host, args.port)
        return
    
    # 运行主循环（带信号处理）
    try:
        if args.once:
            asyncio.run(run_once(config))
        else:
            asyncio.run(run_with_api(config, args))
    except KeyboardInterrupt:
        print("\n收到中断信号...")


async def run_with_api(cfg: ConfigManager, args):
    """运行监控（可选带 API）"""
    global _shutdown_event
    
    loop = asyncio.get_running_loop()
    _shutdown_event = asyncio.Event()
    
    # 注册信号处理（仅 Unix）
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, create_shutdown_handler(loop))
    except NotImplementedError:
        # Windows 不支持 add_signal_handler
        pass
    
    # 启动 API 服务器（如果需要）
    api_task = None
    if args.api:
        api_task = asyncio.create_task(run_api_server_async(args.host, args.port))
        print(f"🌐 API 服务器启动中: http://{args.host}:{args.port}")
    
    # 启动监控
    monitor_task = asyncio.create_task(main_loop(cfg))
    
    # 等待关闭信号
    await _shutdown_event.wait()
    
    # 优雅关闭
    print("\n正在优雅关闭...")
    
    if api_task:
        api_task.cancel()
        try:
            await api_task
        except asyncio.CancelledError:
            pass
    
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    
    await shutdown()


async def run_api_server_async(host: str = "0.0.0.0", port: int = 8000):
    """异步启动 FastAPI 服务器"""
    import uvicorn
    from src.api.app import create_app
    
    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """启动 FastAPI 服务器"""
    import uvicorn
    from src.api.app import create_app
    
    print(f"\n🌐 启动 FastAPI 管理接口...")
    print(f"   地址: http://{host}:{port}")
    print(f"   文档: http://{host}:{port}/docs")
    print(f"   管理面板: http://{host}:{port}/")
    print()
    
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
