# VPS 补货监控系统

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.40+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
[![CI](https://github.com/smysle/vps-stock-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/smysle/vps-stock-monitor/actions/workflows/ci.yml)

**功能强大的 VPS 库存监控工具，支持 CapMonster Cloud 自动打码过 Cloudflare 验证**

</div>

---

## ✨ 功能特性

- 🔍 **多站点监控** - 支持搬瓦工、DMIT、RackNerd、HostDare 等主流 VPS 商家
- 🤖 **自动打码** - 集成 CapMonster Cloud，自动解决 Cloudflare Turnstile/Challenge 验证
- 📱 **多渠道通知** - 支持 Telegram、Discord、邮件、Bark 等多种通知方式
- 🌐 **Web 管理面板** - FastAPI 驱动，实时查看监控状态
- 🔌 **WebSocket 推送** - 库存变化实时推送，无需刷新
- 🐳 **Docker 部署** - 一键部署，开箱即用
- ⚡ **高效稳定** - 基于 Playwright 的浏览器自动化，模拟真实用户行为
- 🔧 **热重载配置** - 修改配置文件自动生效，无需重启
- 🔒 **安全加固** - API 认证、XSS 防护、SSRF 防护等

## 📋 支持的 VPS 商家

| 商家 | 状态 | 说明 |
|------|------|------|
| 搬瓦工 (BandwagonHost) | ✅ | CN2 GIA-E 限量版等 |
| DMIT | ✅ | LAX Pro、HKG Pro 等 |
| RackNerd | ✅ | 黑五特价等 |
| HostDare | ✅ | CN2 GIA 系列 |
| GreenCloudVPS | ✅ | Budget KVM 等 |
| CloudCone | ✅ | 特价 VPS |
| Spartan Host | ✅ | DDoS 防护 VPS |
| BuyVM | ✅ | 大硬盘 VPS |
| 自定义站点 | ✅ | 支持添加任意站点 |

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 克隆项目
git clone https://github.com/smysle/vps-stock-monitor.git
cd vps-stock-monitor

# 复制配置文件
cp config.yaml.example config.yaml

# 编辑配置（填写你的 API Key 和通知设置）
vim config.yaml

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 方式二：本地运行

```bash
# 克隆项目
git clone https://github.com/smysle/vps-stock-monitor.git
cd vps-stock-monitor

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium

# 复制配置文件
cp config.yaml.example config.yaml

# 编辑配置
vim config.yaml

# 启动（监控 + API）
python main.py --api

# 仅启动 API
python main.py --api-only
```

## ⚙️ 配置说明

配置文件使用 YAML 格式，支持热重载：

```yaml
# config.yaml

# CapMonster Cloud 配置（必须）
capmonster:
  api_key: "your_capmonster_api_key"

# 监控配置
monitor:
  check_interval: 300      # 检查间隔（秒）
  retry_interval: 60       # 失败重试间隔
  max_retries: 3           # 最大重试次数

# 通知配置
notifications:
  telegram:
    enabled: true
    bot_token: "your_bot_token"
    chat_id: "your_chat_id"
  
  discord:
    enabled: false
    webhook_url: "your_webhook_url"

# 监控产品列表
products:
  - name: "搬瓦工 CN2 GIA-E"
    url: "https://bandwagonhost.com/cart.php?a=add&pid=87"
    site: "bandwagonhost"
    enabled: true

# API 配置
api:
  enabled: true
  host: "127.0.0.1"
  port: 8000
  auth:
    enabled: true
    api_key: "your_secure_api_key"
```

完整配置示例请参考 [config.yaml.example](config.yaml.example)

## 🌐 Web 管理面板

启动后访问 `http://localhost:8000` 即可使用管理面板：

- **仪表盘** - 查看监控状态、统计信息
- **产品管理** - 添加、编辑、删除监控产品
- **实时日志** - WebSocket 实时推送检查结果
- **手动触发** - 立即检查指定产品

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 系统状态 |
| GET | `/api/products` | 产品列表 |
| POST | `/api/products/{id}/check` | 手动检查 |
| GET | `/api/history` | 检查历史 |
| WS | `/ws` | WebSocket 实时推送 |

API 文档：`http://localhost:8000/docs`

## 🔒 安全特性

本项目经过安全审计，包含以下防护措施：

- ✅ API Key 时序安全比较（防时序攻击）
- ✅ HTML/Markdown 输出转义（防 XSS）
- ✅ URL 验证（防 SSRF）
- ✅ WebSocket 认证 + 连接数限制
- ✅ 敏感信息自动脱敏
- ✅ 配置文件权限检查

## 📁 项目结构

```
vps-stock-monitor/
├── config.yaml.example     # 配置示例
├── config.schema.json      # 配置 JSON Schema
├── main.py                 # 主程序入口
├── Dockerfile              # Docker 构建
├── docker-compose.yml      # Docker Compose
├── requirements.txt        # Python 依赖
└── src/
    ├── api/                # FastAPI Web 应用
    │   ├── app.py          # 应用工厂
    │   ├── routes/         # API 路由
    │   └── static/         # 静态文件
    ├── captcha/            # 验证码解决
    │   ├── capmonster.py   # CapMonster 客户端
    │   └── solver.py       # 验证码解决器
    ├── config/             # 配置管理
    │   └── settings.py     # 配置加载 + 热重载
    ├── core/               # 核心逻辑
    │   ├── browser.py      # 浏览器管理
    │   ├── monitor.py      # 监控逻辑
    │   └── scheduler.py    # 任务调度
    ├── notifications/      # 通知渠道
    │   ├── telegram.py     # Telegram
    │   ├── discord.py      # Discord
    │   └── email.py        # 邮件
    └── utils/              # 工具模块
        ├── security.py     # 安全工具
        ├── retry.py        # 重试机制
        └── affiliate.py    # 推广链接
```

## 🛠️ 开发

```bash
# 安装开发依赖
pip install -r requirements.txt
pip install pytest pytest-asyncio ruff

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/

# 开发模式运行
python main.py --api --debug
```

## 📝 更新日志

### v1.0.0 (2026-01-18)

- 🎉 首次发布
- ✅ 完成安全审计（114 项问题已修复）
- 🔒 Phase 1: 安全漏洞修复 (21 项)
- 🛡️ Phase 2: 稳定性修复 (29 项)
- 💪 Phase 3: 健壮性改进 (33 项)
- ✨ Phase 4: 代码质量优化 (31 项)

## 📄 许可证

MIT License

## 🙏 鸣谢

- [Playwright](https://playwright.dev/) - 浏览器自动化
- [CapMonster Cloud](https://capmonster.cloud/) - 验证码解决服务
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
