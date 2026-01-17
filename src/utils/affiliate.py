"""
Affiliate (推广链接) 管理模块
支持为不同 VPS 商家配置推广链接参数
"""
from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
import re


@dataclass
class AffiliateConfig:
    """单个站点的推广配置"""
    # 推广参数名 (如 aff, affid, ref, referral 等)
    param_name: str
    # 推广 ID
    affiliate_id: str
    # 是否启用
    enabled: bool = True
    # 备注
    note: str = ""


# 各 VPS 商家的推广参数格式
# 不同商家使用不同的参数名
AFFILIATE_PARAM_FORMATS = {
    # 搬瓦工 - 使用 aff 参数
    "bandwagonhost.com": "aff",
    "bwh81.net": "aff",
    "bwh88.net": "aff",
    "bwh89.net": "aff",
    
    # DMIT - 使用 aff 参数
    "dmit.io": "aff",
    
    # RackNerd - 使用 aff 参数
    "racknerd.com": "aff",
    "my.racknerd.com": "aff",
    
    # HostDare - 使用 aff 参数
    "hostdare.com": "aff",
    "manage.hostdare.com": "aff",
    
    # GreenCloudVPS - 使用 aff 参数
    "greencloudvps.com": "aff",
    
    # CloudCone - 使用 ref 参数
    "cloudcone.com": "ref",
    "app.cloudcone.com": "ref",
    
    # Spartan Host - 使用 aff 参数
    "spartanhost.net": "aff",
    "billing.spartanhost.net": "aff",
    
    # BuyVM/Frantech - 使用 aff 参数
    "buyvm.net": "aff",
    "my.frantech.ca": "aff",
    
    # Vultr - 使用 ref 参数
    "vultr.com": "ref",
    
    # DigitalOcean - 使用 refcode 参数
    "digitalocean.com": "refcode",
    
    # Linode - 使用 r 参数
    "linode.com": "r",
    
    # Hosteons - 使用 aff 参数
    "hosteons.com": "aff",
    
    # AlphaVPS - 使用 aff 参数
    "alphavps.com": "aff",
    
    # Contabo - 无标准推广参数，通常使用专属链接
    "contabo.com": None,
    
    # Hetzner - 使用 ref 参数
    "hetzner.com": "ref",
}


def _match_domain(url_domain: str, config_domain: str) -> bool:
    """
    安全的域名匹配
    
    Args:
        url_domain: URL 中的域名
        config_domain: 配置中的域名
        
    Returns:
        是否匹配
    """
    url_domain = url_domain.lower().strip()
    config_domain = config_domain.lower().strip()
    
    # 精确匹配
    if url_domain == config_domain:
        return True
    
    # 子域名匹配：url_domain 必须以 .config_domain 结尾
    # 例如：my.racknerd.com 匹配 racknerd.com
    if url_domain.endswith('.' + config_domain):
        return True
    
    return False


class AffiliateManager:
    """推广链接管理器"""
    
    def __init__(self):
        # 存储各站点的推广配置
        self._configs: Dict[str, AffiliateConfig] = {}
    
    def set_affiliate(
        self,
        domain: str,
        affiliate_id: str,
        param_name: Optional[str] = None,
        enabled: bool = True,
        note: str = ""
    ):
        """
        设置站点的推广配置
        
        Args:
            domain: 站点域名 (如 bandwagonhost.com)
            affiliate_id: 推广 ID
            param_name: 参数名 (可选，默认自动检测)
            enabled: 是否启用
            note: 备注
        """
        # 规范化域名
        domain = domain.lower().strip()
        
        # 自动检测参数名
        if param_name is None:
            param_name = self._get_param_name(domain)
        
        if param_name:
            self._configs[domain] = AffiliateConfig(
                param_name=param_name,
                affiliate_id=affiliate_id,
                enabled=enabled,
                note=note
            )
    
    def remove_affiliate(self, domain: str):
        """移除站点的推广配置"""
        domain = domain.lower().strip()
        if domain in self._configs:
            del self._configs[domain]
    
    def get_affiliate(self, domain: str) -> Optional[AffiliateConfig]:
        """获取站点的推广配置"""
        domain = domain.lower().strip()
        return self._configs.get(domain)
    
    def _get_param_name(self, domain: str) -> Optional[str]:
        """获取站点的推广参数名"""
        domain = domain.lower().strip()
        
        # 精确匹配
        if domain in AFFILIATE_PARAM_FORMATS:
            return AFFILIATE_PARAM_FORMATS[domain]
        
        # 安全的子域名匹配
        for known_domain, param in AFFILIATE_PARAM_FORMATS.items():
            if _match_domain(domain, known_domain):
                return param
        
        # 默认使用 aff
        return "aff"
    
    def _extract_domain(self, url: str) -> str:
        """从 URL 提取域名"""
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    def add_affiliate_to_url(self, url: str) -> str:
        """
        为 URL 添加推广参数
        
        Args:
            url: 原始 URL
            
        Returns:
            添加了推广参数的 URL
        """
        domain = self._extract_domain(url)
        if not domain:
            return url
        
        # 查找匹配的配置（使用安全匹配）
        config = None
        for cfg_domain, cfg in self._configs.items():
            if _match_domain(domain, cfg_domain):
                config = cfg
                break
        
        if not config or not config.enabled:
            return url
        
        # 解析 URL
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        
        # 添加推广参数（如果不存在）
        if config.param_name not in query_params:
            query_params[config.param_name] = [config.affiliate_id]
        
        # 重建 URL
        # 将列表值转换为单个值
        flat_params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
        new_query = urlencode(flat_params, doseq=True)
        
        new_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        return new_url
    
    def get_all_configs(self) -> Dict[str, AffiliateConfig]:
        """获取所有推广配置"""
        return self._configs.copy()
    
    def load_from_dict(self, data: Dict[str, Dict]):
        """
        从字典加载配置
        
        格式:
        {
            "bandwagonhost.com": {"affiliate_id": "12345"},
            "dmit.io": {"affiliate_id": "67890", "enabled": true}
        }
        """
        for domain, config in data.items():
            self.set_affiliate(
                domain=domain,
                affiliate_id=config.get("affiliate_id", ""),
                param_name=config.get("param_name"),
                enabled=config.get("enabled", True),
                note=config.get("note", "")
            )
    
    def to_dict(self) -> Dict[str, Dict]:
        """导出配置为字典"""
        return {
            domain: {
                "param_name": cfg.param_name,
                "affiliate_id": cfg.affiliate_id,
                "enabled": cfg.enabled,
                "note": cfg.note
            }
            for domain, cfg in self._configs.items()
        }


# 全局推广管理器实例
affiliate_manager = AffiliateManager()


def setup_affiliates(affiliates: Dict[str, str]):
    """
    快速设置推广配置
    
    Args:
        affiliates: {域名: 推广ID} 字典
        
    示例:
        setup_affiliates({
            "bandwagonhost.com": "12345",
            "dmit.io": "67890",
            "racknerd.com": "11111",
        })
    """
    for domain, aff_id in affiliates.items():
        affiliate_manager.set_affiliate(domain, aff_id)


def get_affiliate_url(url: str) -> str:
    """
    获取添加了推广参数的 URL
    
    Args:
        url: 原始 URL
        
    Returns:
        添加了推广参数的 URL
    """
    return affiliate_manager.add_affiliate_to_url(url)
