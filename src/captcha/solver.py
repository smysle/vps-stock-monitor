"""
验证码解决器 - 统一接口
"""
import re
import json
import asyncio
import logging
from typing import Optional, Tuple
from playwright.async_api import Page

from .capmonster import CapMonsterClient, TaskResult


logger = logging.getLogger(__name__)


class CaptchaSolver:
    """验证码解决器"""
    
    def __init__(self, capmonster: CapMonsterClient):
        self.capmonster = capmonster
    
    async def detect_captcha_type(self, page: Page) -> Tuple[Optional[str], Optional[str]]:
        """
        检测页面上的验证码类型
        
        Returns:
            (captcha_type, sitekey) - 验证码类型和 sitekey
        """
        content = await page.content()
        
        # 检测 Cloudflare Turnstile
        turnstile_iframe = await page.query_selector(
            'iframe[src*="challenges.cloudflare.com/turnstile"]'
        )
        if turnstile_iframe:
            src = await turnstile_iframe.get_attribute("src") or ""
            sitekey = self._extract_turnstile_key(src, content)
            if sitekey:
                return "turnstile", sitekey
        
        # 检测 Turnstile 容器
        turnstile_container = await page.query_selector('[data-sitekey]')
        if turnstile_container:
            sitekey = await turnstile_container.get_attribute("data-sitekey")
            if sitekey:
                return "turnstile", sitekey
        
        # 检测 Cloudflare Challenge (5秒盾)
        cf_challenge_indicators = [
            "Just a moment...",
            "Checking your browser",
            "cf-browser-verification",
            "cf_chl_opt",
            "Verifying you are human",
            "DDoS protection by Cloudflare"
        ]
        if any(indicator in content for indicator in cf_challenge_indicators):
            return "cloudflare_challenge", None
        
        # 检测 reCAPTCHA v2
        recaptcha_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
        if recaptcha_match and "recaptcha" in content.lower():
            return "recaptcha_v2", recaptcha_match.group(1)
        
        # 检测 hCaptcha
        hcaptcha_match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
        if hcaptcha_match and "hcaptcha" in content.lower():
            return "hcaptcha", hcaptcha_match.group(1)
        
        return None, None
    
    def _extract_turnstile_key(self, iframe_src: str, page_content: str) -> Optional[str]:
        """从 iframe src 或页面内容提取 Turnstile sitekey"""
        # 从 iframe src 提取
        match = re.search(r'[?&]k=([^&]+)', iframe_src)
        if match:
            return match.group(1)
        
        # 从页面内容提取
        patterns = [
            r'turnstile\.render\([^)]*sitekey["\s:]+["\']([^"\']+)["\']',
            r'data-sitekey=["\']([^"\']+)["\']',
            r'sitekey["\s:]+["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, page_content)
            if match:
                return match.group(1)
        
        return None
    
    async def solve(
        self,
        page: Page,
        website_url: str,
        captcha_type: Optional[str] = None,
        sitekey: Optional[str] = None
    ) -> TaskResult:
        """
        解决验证码
        
        Args:
            page: Playwright 页面对象
            website_url: 网站 URL
            captcha_type: 验证码类型 (可选，自动检测)
            sitekey: sitekey (可选，自动检测)
        """
        # 自动检测验证码类型
        if not captcha_type:
            captcha_type, detected_sitekey = await self.detect_captcha_type(page)
            if not sitekey:
                sitekey = detected_sitekey
        
        if not captcha_type:
            return TaskResult(
                success=False,
                error_code="NO_CAPTCHA",
                error_description="未检测到验证码"
            )
        
        logger.info(f"检测到验证码类型: {captcha_type}, sitekey: {sitekey}")
        
        # 根据类型解决验证码
        if captcha_type == "turnstile":
            if not sitekey:
                return TaskResult(
                    success=False,
                    error_code="NO_SITEKEY",
                    error_description="未找到 Turnstile sitekey"
                )
            return await self.capmonster.solve_turnstile(
                website_url=website_url,
                website_key=sitekey
            )
        
        elif captcha_type == "cloudflare_challenge":
            # Cloudflare Challenge 需要代理
            logger.warning("Cloudflare Challenge 需要代理支持，尝试等待自动通过...")
            # 等待一段时间看是否自动通过
            import asyncio
            await asyncio.sleep(6)
            
            # 检查是否还有验证
            new_type, _ = await self.detect_captcha_type(page)
            if not new_type:
                return TaskResult(success=True, token="auto_passed")
            
            return TaskResult(
                success=False,
                error_code="CF_CHALLENGE",
                error_description="Cloudflare Challenge 需要代理支持"
            )
        
        elif captcha_type == "recaptcha_v2":
            if not sitekey:
                return TaskResult(
                    success=False,
                    error_code="NO_SITEKEY",
                    error_description="未找到 reCAPTCHA sitekey"
                )
            return await self.capmonster.solve_recaptcha_v2(
                website_url=website_url,
                website_key=sitekey
            )
        
        elif captcha_type == "hcaptcha":
            if not sitekey:
                return TaskResult(
                    success=False,
                    error_code="NO_SITEKEY",
                    error_description="未找到 hCaptcha sitekey"
                )
            return await self.capmonster.solve_hcaptcha(
                website_url=website_url,
                website_key=sitekey
            )
        
        return TaskResult(
            success=False,
            error_code="UNKNOWN_TYPE",
            error_description=f"不支持的验证码类型: {captcha_type}"
        )
    
    async def inject_token(
        self,
        page: Page,
        token: str,
        captcha_type: str = "turnstile"
    ) -> bool:
        """
        将验证码 token 注入页面（安全参数化）
        
        Args:
            page: Playwright 页面对象
            token: 验证码 token
            captcha_type: 验证码类型
        """
        try:
            if captcha_type == "turnstile":
                # 使用 Playwright 的参数传递机制，避免 JavaScript 注入
                await page.evaluate('''(token) => {
                    // 设置隐藏字段
                    var inputs = document.querySelectorAll(
                        '[name="cf-turnstile-response"], ' +
                        '[name="g-recaptcha-response"], ' +
                        'input[name*="turnstile"]'
                    );
                    inputs.forEach(function(input) {
                        input.value = token;
                    });
                    
                    // 尝试触发回调
                    if (typeof window.turnstileCallback === 'function') {
                        window.turnstileCallback(token);
                    }
                    if (typeof window.onTurnstileSuccess === 'function') {
                        window.onTurnstileSuccess(token);
                    }
                    
                    // 触发表单提交事件
                    var form = document.querySelector('form');
                    if (form) {
                        var event = new Event('submit', { bubbles: true, cancelable: true });
                        form.dispatchEvent(event);
                    }
                }''', token)
                return True
            
            elif captcha_type in ["recaptcha_v2", "hcaptcha"]:
                # 使用参数化注入
                await page.evaluate('''(token) => {
                    var textarea = document.querySelector('[name="g-recaptcha-response"], [name="h-captcha-response"]');
                    if (textarea) {
                        textarea.value = token;
                    }
                    
                    // 尝试触发回调
                    if (typeof window.grecaptcha !== 'undefined' && window.grecaptcha.callback) {
                        window.grecaptcha.callback(token);
                    }
                }''', token)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"注入 token 失败: {e}")
            return False
