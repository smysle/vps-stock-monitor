"""
产品管理 API
"""
import json
import logging
import hashlib
import re
import ipaddress
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Path
import redis.asyncio as redis
from redis.exceptions import RedisError

from ..schemas import (
    ProductCreate, ProductUpdate, ProductResponse, 
    ProductListResponse, ProductStatus, SuccessResponse
)
from ..deps import get_redis, get_config_dep
from ...config.settings import ConfigManager

logger = logging.getLogger(__name__)
router = APIRouter()

# SSRF 防护配置
ALLOWED_SCHEMES = {'http', 'https'}
BLOCKED_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '169.254.169.254'}
BLOCKED_NETWORKS = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('169.254.0.0/16'),
]

# product_id 格式验证
PRODUCT_ID_PATTERN = re.compile(r'^[a-f0-9]{16}$')


def safe_float(value, default=None):
    """安全转换为浮点数"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default: int = 0) -> int:
    """安全转换为整数"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def validate_product_url(url: str) -> None:
    """验证产品 URL，防止 SSRF"""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(400, f"URL scheme not allowed: {parsed.scheme}")
    
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(400, "Invalid URL: no hostname")
    
    if hostname in BLOCKED_HOSTS:
        raise HTTPException(400, "Internal URLs not allowed")
    
    # 检查是否为 IP 地址
    try:
        ip = ipaddress.ip_address(hostname)
        for network in BLOCKED_NETWORKS:
            if ip in network:
                raise HTTPException(400, "Internal IP addresses not allowed")
    except ValueError:
        pass  # 不是 IP 地址，是域名


def validate_product_id(product_id: str) -> str:
    """验证 product_id 格式"""
    if not PRODUCT_ID_PATTERN.match(product_id):
        raise HTTPException(400, "Invalid product ID format")
    return product_id

# Redis Keys
PRODUCTS_KEY = "vps_monitor:products"
PRODUCT_STATUS_KEY = "vps_monitor:product_status:{product_id}"
PRODUCT_HISTORY_KEY = "vps_monitor:product_history:{product_id}"


def generate_product_id(url: str) -> str:
    """生成产品 ID（使用 SHA256）"""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


async def get_product_from_redis(
    redis_client: Optional[redis.Redis], 
    product_id: str
) -> Optional[dict]:
    """从 Redis 获取产品"""
    if not redis_client:
        return None
    try:
        data = await redis_client.hget(PRODUCTS_KEY, product_id)
        if data:
            return json.loads(data)
    except RedisError as e:
        logger.error(f"Redis 读取失败: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
    return None


async def save_product_to_redis(
    redis_client: Optional[redis.Redis],
    product_id: str,
    product: dict
):
    """保存产品到 Redis"""
    if not redis_client:
        return
    try:
        await redis_client.hset(PRODUCTS_KEY, product_id, json.dumps(product, default=str))
    except RedisError as e:
        logger.error(f"Redis 写入失败: {e}")


async def delete_product_from_redis(
    redis_client: Optional[redis.Redis],
    product_id: str
):
    """从 Redis 删除产品"""
    if not redis_client:
        return
    try:
        await redis_client.hdel(PRODUCTS_KEY, product_id)
        await redis_client.delete(PRODUCT_STATUS_KEY.format(product_id=product_id))
    except RedisError as e:
        logger.error(f"Redis 删除失败: {e}")


@router.get("", response_model=ProductListResponse)
async def list_products(
    enabled_only: bool = Query(False, description="只显示启用的产品"),
    redis_client: redis.Redis = Depends(get_redis),
    config: ConfigManager = Depends(get_config_dep)
):
    """获取产品列表"""
    products = []
    
    # 优先从 Redis 获取
    if redis_client:
        try:
            all_products = await redis_client.hgetall(PRODUCTS_KEY)
            
            if all_products:
                # 使用 Pipeline 批量获取状态（解决 N+1 问题）
                product_ids = list(all_products.keys())
                
                pipe = redis_client.pipeline()
                for product_id in product_ids:
                    status_key = PRODUCT_STATUS_KEY.format(product_id=product_id)
                    pipe.hgetall(status_key)
                
                status_results = await pipe.execute()
                
                for i, (product_id, data) in enumerate(all_products.items()):
                    try:
                        product = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    
                    product['id'] = product_id
                    
                    # 从批量结果获取状态
                    status_data = status_results[i] if i < len(status_results) else {}
                    if status_data:
                        product['status'] = status_data.get('status', ProductStatus.UNKNOWN)
                        product['price'] = float(status_data['price']) if status_data.get('price') else None
                        product['last_checked'] = status_data.get('last_checked')
                        product['last_in_stock'] = status_data.get('last_in_stock')
                        product['check_count'] = int(status_data.get('check_count', 0))
                    
                    products.append(product)
        except RedisError as e:
            logger.error(f"Redis 读取失败: {e}")
    
    # 如果 Redis 为空，从配置加载
    if not products:
        for p in config.products:
            product_id = generate_product_id(p.url)
            products.append({
                'id': product_id,
                'name': p.name,
                'url': p.url,
                'site': p.site,
                'enabled': p.enabled,
                'description': p.description,
                'check_interval': p.check_interval,
                'status': ProductStatus.UNKNOWN,
                'price': None,
                'last_checked': None,
                'last_in_stock': None,
                'check_count': 0
            })
            
            # 保存到 Redis
            if redis_client:
                await save_product_to_redis(redis_client, product_id, {
                    'name': p.name,
                    'url': p.url,
                    'site': p.site,
                    'enabled': p.enabled,
                    'description': p.description,
                    'check_interval': p.check_interval
                })
    
    # 过滤
    if enabled_only:
        products = [p for p in products if p.get('enabled', True)]
    
    return ProductListResponse(
        total=len(products),
        items=[ProductResponse(**p) for p in products]
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str = Path(..., regex="^[a-f0-9]{16}$"),
    redis_client: redis.Redis = Depends(get_redis)
):
    """获取单个产品"""
    # 验证 product_id 格式
    validate_product_id(product_id)
    
    product = await get_product_from_redis(redis_client, product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    
    product['id'] = product_id
    
    # 获取状态
    if redis_client:
        status_key = PRODUCT_STATUS_KEY.format(product_id=product_id)
        status_data = await redis_client.hgetall(status_key)
        if status_data:
            product['status'] = status_data.get('status', ProductStatus.UNKNOWN)
            product['price'] = float(status_data['price']) if status_data.get('price') else None
            product['last_checked'] = status_data.get('last_checked')
            product['last_in_stock'] = status_data.get('last_in_stock')
            product['check_count'] = int(status_data.get('check_count', 0))
    
    return ProductResponse(**product)


@router.post("", response_model=ProductResponse)
async def create_product(
    product: ProductCreate,
    redis_client: redis.Redis = Depends(get_redis)
):
    """创建产品"""
    # SSRF 防护：验证 URL
    validate_product_url(product.url)
    
    product_id = generate_product_id(product.url)
    
    # 检查是否已存在
    existing = await get_product_from_redis(redis_client, product_id)
    if existing:
        raise HTTPException(status_code=409, detail="产品已存在")
    
    # 保存产品
    product_data = product.model_dump()
    await save_product_to_redis(redis_client, product_id, product_data)
    
    logger.info(f"创建产品: {product.name} ({product_id})")
    
    return ProductResponse(
        id=product_id,
        **product_data,
        status=ProductStatus.UNKNOWN
    )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str = Path(..., regex="^[a-f0-9]{16}$"),
    update: ProductUpdate = None,
    redis_client: redis.Redis = Depends(get_redis)
):
    """更新产品"""
    # 验证 product_id 格式
    validate_product_id(product_id)
    
    # 如果更新包含 URL，验证 URL
    if update and hasattr(update, 'url') and update.url:
        validate_product_url(update.url)
    
    product = await get_product_from_redis(redis_client, product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    
    # 更新字段
    update_data = update.model_dump(exclude_unset=True)
    product.update(update_data)
    
    await save_product_to_redis(redis_client, product_id, product)
    
    logger.info(f"更新产品: {product_id}")
    
    product['id'] = product_id
    return ProductResponse(**product, status=ProductStatus.UNKNOWN)


@router.delete("/{product_id}", response_model=SuccessResponse)
async def delete_product(
    product_id: str = Path(..., regex="^[a-f0-9]{16}$"),
    redis_client: redis.Redis = Depends(get_redis)
):
    """删除产品"""
    # 验证 product_id 格式
    validate_product_id(product_id)
    
    product = await get_product_from_redis(redis_client, product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    
    await delete_product_from_redis(redis_client, product_id)
    
    logger.info(f"删除产品: {product_id}")
    
    return SuccessResponse(message=f"产品 {product_id} 已删除")


@router.post("/{product_id}/toggle", response_model=ProductResponse)
async def toggle_product(
    product_id: str = Path(..., regex="^[a-f0-9]{16}$"),
    redis_client: redis.Redis = Depends(get_redis)
):
    """切换产品启用状态"""
    # 验证 product_id 格式
    validate_product_id(product_id)
    
    product = await get_product_from_redis(redis_client, product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    
    product['enabled'] = not product.get('enabled', True)
    await save_product_to_redis(redis_client, product_id, product)
    
    status_str = "启用" if product['enabled'] else "禁用"
    logger.info(f"产品 {product_id} 已{status_str}")
    
    product['id'] = product_id
    return ProductResponse(**product, status=ProductStatus.UNKNOWN)


@router.post("/{product_id}/check", response_model=SuccessResponse)
async def trigger_check(
    product_id: str,
    redis_client: redis.Redis = Depends(get_redis)
):
    """触发单个产品检查"""
    product = await get_product_from_redis(redis_client, product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="产品不存在")
    
    # 发布检查任务到 Redis
    if redis_client:
        await redis_client.publish("vps_monitor:check_product", product_id)
    
    return SuccessResponse(message=f"已触发产品 {product_id} 的检查")


@router.post("/sync", response_model=SuccessResponse)
async def sync_products_from_config(
    redis_client: redis.Redis = Depends(get_redis),
    config: ConfigManager = Depends(get_config_dep)
):
    """从配置文件同步产品列表"""
    synced = 0
    
    if redis_client:
        try:
            # 使用 Pipeline 批量写入
            pipe = redis_client.pipeline()
            
            for p in config.products:
                product_id = generate_product_id(p.url)
                product_data = {
                    'name': p.name,
                    'url': p.url,
                    'site': p.site,
                    'enabled': p.enabled,
                    'description': p.description,
                    'check_interval': p.check_interval
                }
                pipe.hset(PRODUCTS_KEY, product_id, json.dumps(product_data, default=str))
                synced += 1
            
            await pipe.execute()
            logger.info(f"从配置同步了 {synced} 个产品")
        except RedisError as e:
            logger.error(f"同步产品失败: {e}")
            raise HTTPException(status_code=500, detail="同步失败")
    else:
        raise HTTPException(status_code=503, detail="Redis 不可用")
    
    return SuccessResponse(message=f"同步完成，共 {synced} 个产品")
