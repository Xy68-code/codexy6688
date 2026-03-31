# 微信小程序商品监控系统

实时监控微信小程序商品价格，支持多种通知方式。

## 功能特性

- 定时监控商品价格/库存
- 支持多种告警条件（目标价、降价幅度、库存）
- 多种通知方式（Discord、企业微信、邮件）
- 历史记录持久化（SQLite + JSON）
- 支持后台运行

## 项目结构

```
wechat-monitor/
├── config/
│   └── settings.yaml      # 配置文件
├── core/
│   ├── __init__.py
│   ├── api_client.py      # 微信 API 客户端
│   └── monitor.py         # 监控核心模块
├── alert/
│   ├── __init__.py
│   └── notifier.py        # 通知模块
├── data/                   # 数据存储目录
├── logs/                   # 日志目录
├── main.py                 # 主程序入口
└── requirements.txt        # Python 依赖
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

编辑 `config/settings.yaml`：

```yaml
# 商品信息
products:
  - id: "MlAPdY61pKwy3zv"
    name: "DRUNKBAKER 精选商品"
    target_price: 29.9    # 目标价格
    target_stock: 10      # 库存告警阈值
    enabled: true

# 通知配置
alert:
  discord:
    enabled: true
    webhook_url: "https://discord.com/api/webhooks/..."
```

### 3. 运行

```bash
# 前台运行
python main.py

# 后台运行
python main.py --daemon

# 查看状态
python main.py --status

# 测试通知
python main.py --test
```

## 后台运行

### 方式一：nohup

```bash
nohup python main.py > monitor.log 2>&1 &
```

### 方式二：--daemon 参数

```bash
python main.py --daemon
```

### 方式三：systemd（推荐生产环境）

```ini
[Unit]
Description=WeChat Product Monitor
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/clawd/wechat-monitor
ExecStart=/usr/bin/python3 main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 配置说明

### 监控配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `monitor.interval` | 监控间隔（秒） | 120 |
| `monitor.request_timeout` | 请求超时（秒） | 30 |
| `monitor.max_retries` | 最大重试次数 | 3 |
| `monitor.price_threshold` | 降价告警阈值（比例） | 0.05 |

### 告警条件

1. **价格低于目标价** - `target_price > 0` 且当前价格 ≤ 目标价
2. **价格大幅下降** - 相比上次检查降幅超过 `price_threshold`
3. **库存紧张** - 库存 > 0 且 ≤ `stock_threshold`
4. **补货通知** - 从 0 库存变为有货

### 通知渠道

#### Discord

```yaml
alert:
  discord:
    enabled: true
    webhook_url: "https://discord.com/api/webhooks/ID/TOKEN"
    mention_role_id: "123456789"  # 可选
```

#### 企业微信

```yaml
alert:
  wechat_work:
    enabled: true
    webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=KEY"
```

#### 邮件

```yaml
alert:
  email:
    enabled: true
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    use_tls: true
    username: "your_email@gmail.com"
    password: "your_app_password"
    recipients:
      - "recipient@example.com"
```

## Playwright 模式

对于无法直接调用 API 的小程序，可使用浏览器自动化方式：

```yaml
monitor:
  use_playwright: true

playwright:
  headless: true
  viewport_width: 375
  viewport_height: 812
```

安装 Playwright：

```bash
pip install playwright
playwright install chromium
```

## API

### 查看统计

```python
from core.monitor import ProductMonitor

monitor = ProductMonitor(config)

# 获取价格历史
history = monitor.get_price_history("product_id", days=7)

# 获取告警历史
alerts = monitor.get_alert_history("product_id", days=7)

# 获取统计信息
stats = monitor.get_statistics(days=7)
```

## 注意事项

1. **监控间隔** - 建议不低于 60 秒，避免触发反爬
2. **API Token** - 需要抓包获取小程序的 API token
3. **冷却时间** - 默认 600 秒，避免重复告警

## 许可证

MIT License
