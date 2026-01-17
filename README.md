# VPS 补货监控系统

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.40+-green.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**一个功能强大的 VPS 库存监控工具，支持 CapMonster Cloud 自动打码过 Cloudflare 验证**

</div>

---

## ✨ 功能特性

- 🔍 **多站点监控** - 支持搬瓦工、DMIT、RackNerd、HostDare 等主流 VPS 商家
- 🤖 **自动打码** - 集成 CapMonster Cloud，自动解决 Cloudflare Turnstile/Challenge 验证
- 📱 **多渠道通知** - 支持 Telegram、Discord、邮件等多种通知方式
- 🐳 **Docker 部署** - 一键部署，开箱即用
- ⚡ **高效稳定** - 基于 Playwright 的浏览器自动化，模拟真实用户行为
- 🔧 **灵活配置** - 支持自定义监控间隔、产品列表、通知规则

## 📋 支持的 VPS 商家

| 商家 | 状态 | 说明 |
|------|------|------|
| 搬瓦工 (BandwagonHost) | ✅ | CN2 GIA-E 限量版等 |
| DMIT | ✅ | LAX Pro、HKG Pro 等 |
| RackNerd | ✅ | 黑五特价等 |
| HostDare | ✅ | CN2 GIA 系列 |
| GreenCloudVPS | ✅ | Budget KVM 等 |
| CloudCone | ✅ | 特价 VPS |
| 自定义站点 | ✅ | 支持添加任意站点 |

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

1. **克隆项目**
```bash
git clone https://github.com/your-repo/vps-stock-monitor.git
cd vps-stock-monitor
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填写你的配置
```

3. **启动服务**
```bash
docker-compose up -d
```

4. **查看日志**
```bash
docker-compose logs -f
```

### 方式二：本地运行

1. **安装依赖**
```bash
pip install -r requirements.txt
playwright install chromium
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件
```

3. **运行**
```bash
python main.py
```

## ⚙️ 配置说明

### 环境变量

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `CAPMONSTER_API_KEY` | ✅ | CapMonster Cloud API Key |
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | ✅ | Telegram Chat ID |
| `DISCORD_WEBHOOK_URL` | ❌ | Discord Webhook URL |
| `CHECK_INTERVAL` | ❌ | 检查间隔（秒），默认 300 |
| `HEADLESS` | ❌ | 无头模式，默认 true |
| `PROXY_URL` | ❌ | 代理服务器 URL |

### 添加自定义产品

编辑 `src/config/products.py`：

```python
from src.config.products import Product, PRODUCTS

# 添加新产品
PRODUCTS.append(Product(
    name="我的 VPS",
    url="https://example.com/cart.php?a=add&pid=123",
    site="example.com",
    description="自定义 VPS 产品",
    enabled=True,
))
```

## 📱 获取 Telegram 配置

1. **创建 Bot**
   - 在 Telegram 中搜索 `@BotFather`
   - 发送 `/newbot` 创建新 Bot
   - 保存获得的 Token

2. **获取 Chat ID**
   - 向你的 Bot 发送任意消息
   - 访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - 找到 `chat.id` 字段

## 🔑 获取 CapMonster Cloud API Key

1. 访问 [CapMonster Cloud](https://capmonster.cloud)
2. 注册账号并充值
3. 在控制台获取 API Key

**价格参考：**
- Cloudflare Turnstile: $1.30 / 1000次
- Cloudflare Challenge: $2.20 / 1000次

## 📁 项目结构

```
vps-stock-monitor/
├── src/
│   ├── captcha/          # 验证码处理模块
│   │   ├── capmonster.py # CapMonster Cloud 客户端
│   │   └── solver.py     # 验证码解决器
│   ├── config/           # 配置模块
│   │   ├── settings.py   # 应用配置
│   │   └── products.py   # 产品配置
│   ├── core/             # 核心模块
│   │   ├── browser.py    # 浏览器管理
│   │   ├── monitor.py    # 监控引擎
│   │   └── scheduler.py  # 任务调度
│   ├── notifications/    # 通知模块
│   │   ├── telegram.py   # Telegram 通知
│   │   ├── discord.py    # Discord 通知
│   │   └── email.py      # 邮件通知
│   └── utils/            # 工具模块
├── main.py               # 主程序入口
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## 🔧 命令行参数

```bash
# 启动监控
python main.py

# 执行一次检查
python main.py --once

# 设置检查间隔
python main.py --interval 60

# 显示浏览器窗口（调试用）
python main.py --headless false

# 指定配置文件
python main.py --config /path/to/config.json

# 监控指定 URL
python main.py --products https://example.com/product1 https://example.com/product2
```

## 📊 通知示例

### Telegram 通知

```
🎉 VPS 补货通知

📦 产品: 搬瓦工 CN2 GIA-E 限量版
📝 描述: CN2 GIA-E 限量版，1核/1G/20G SSD/1T流量
💰 价格: $49.99
📊 状态: In Stock

🔗 链接: https://bandwagonhost.com/cart.php?a=add&pid=87

⏰ 快去抢购吧！
```

## ⚠️ 注意事项

1. **合理设置检查间隔** - 建议不低于 60 秒，避免被封 IP
2. **使用代理** - 如果频繁被封，建议配置代理
3. **CapMonster 余额** - 确保账户有足够余额
4. **遵守服务条款** - 请合理使用，不要滥用

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- [Playwright](https://playwright.dev/) - 浏览器自动化框架
- [CapMonster Cloud](https://capmonster.cloud/) - 验证码识别服务
- [changedetection.io](https://github.com/dgtlmoon/changedetection.io) - 灵感来源
