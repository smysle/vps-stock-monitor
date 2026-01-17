"""
FastAPI 应用工厂
"""
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from .routes import products, status, system, websocket
from .deps import init_redis, close_redis
from ..config.settings import ConfigManager, get_config
from ..constants import VERSION

logger = logging.getLogger(__name__)

_app: Optional[FastAPI] = None

# API Key 认证
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)) -> Optional[str]:
    """验证 API Key（使用时序安全比较）"""
    config = get_config()
    auth_config = config.get('api.auth', {})
    
    if not auth_config.get('enabled', False):
        return None  # 认证未启用，直接通过
    
    expected_key = auth_config.get('api_key', '')
    if not expected_key:
        return None  # 未配置 key，直接通过
    
    # 使用 hmac.compare_digest 防止时序攻击
    if not api_key or not hmac.compare_digest(api_key.encode('utf-8'), expected_key.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    return api_key


async def verify_ws_token(token: Optional[str] = Query(None)) -> bool:
    """验证 WebSocket Token"""
    config = get_config()
    auth_config = config.get('api.auth', {})
    
    if not auth_config.get('enabled', False):
        return True  # 认证未启用
    
    expected_key = auth_config.get('api_key', '')
    if not expected_key:
        return True  # 未配置 key
    
    if not token:
        return False
    
    return hmac.compare_digest(token.encode('utf-8'), expected_key.encode('utf-8'))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    config = get_config()
    
    # 启动时
    logger.info("FastAPI 管理接口启动中...")
    
    # 初始化 Redis
    await init_redis()
    logger.info("Redis 初始化完成")
    
    # 只有在未启动监听时才启动（避免重复）
    if config._observer is None:
        config.start_watching()
        logger.info("配置文件监听已启动")
    
    yield
    
    # 关闭时
    logger.info("FastAPI 管理接口关闭中...")
    
    # 关闭 Redis
    await close_redis()
    logger.info("资源清理完成")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    global _app
    
    config = get_config()
    
    app = FastAPI(
        title="VPS 补货监控系统",
        description="VPS 库存监控管理 API",
        version=VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )
    
    # CORS 中间件 - 从配置读取允许的源
    cors_origins = config.get('api.cors_origins', ['*'])
    # 如果允许所有源，则不允许凭证
    allow_credentials = '*' not in cors_origins
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # 注册路由（敏感路由需要认证）
    app.include_router(
        products.router, 
        prefix="/api/products", 
        tags=["产品管理"],
        dependencies=[Depends(verify_api_key)]
    )
    app.include_router(
        status.router, 
        prefix="/api/status", 
        tags=["状态查询"]
    )
    app.include_router(
        system.router, 
        prefix="/api/system", 
        tags=["系统管理"],
        dependencies=[Depends(verify_api_key)]
    )
    app.include_router(
        websocket.router, 
        prefix="/ws", 
        tags=["WebSocket"]
    )
    
    # 静态文件（管理面板）
    try:
        app.mount("/", StaticFiles(directory="src/api/static", html=True), name="static")
    except Exception:
        logger.warning("静态文件目录不存在，跳过挂载")
    
    _app = app
    return app


def get_app() -> FastAPI:
    """获取应用实例"""
    global _app
    if _app is None:
        _app = create_app()
    return _app
