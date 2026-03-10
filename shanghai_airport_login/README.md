 自动登录脚本

> 基于 Puppeteer 的自动化登录工具，支持滑块验证码自动识别

## 功能特性

- 🤖 自动填写用户名和密码
- 🧩 自动处理滑块验证码（图像识别 + 轨迹模拟）
- 🔍 自动检测并启动系统 Chrome/Chromium 浏览器
- ⚙️ 支持配置化（无头模式、调试开关、超时设置）
- 📸 登录失败时自动保存截图

## 环境要求

- Node.js 18+
- Chrome 或 Chromium 浏览器

## 快速开始

### 1. 安装依赖

```bash
cd shanghai_airport_login
npm install
```

### 2. 配置账号

复制配置示例文件并修改：

```bash
cp config.example.json config.json
```

编辑 `config.json`，填入实际的用户名和密码：

```json
{
  "loginUrl": "https://sms.shanghaiairport.com",
  "username": "你的用户名",
  "password": "你的密码",
  "headless": false,
  "debug": true
}
```

### 3. 运行脚本

```bash
npm start
# 或
node index.js
```

## 配置说明

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `loginUrl` | string | 登录页面 URL | - |
| `username` | string | 用户名 | - |
| `password` | string | 密码 | - |
| `headless` | boolean | 是否无头模式运行 | `false` |
| `slowMo` | number | 操作延迟(毫秒) | `50` |
| `debug` | boolean | 开启调试模式(保存截图) | `true` |
| `timeout` | number | 超时时间(毫秒) | `30000` |
| `slider.maxRetries` | number | 滑块验证码最大重试次数 | `3` |

## 目录结构

```
shanghai_airport_login/
├── index.js           # 主入口
├── login.js           # 登录逻辑
├── config.json        # 配置文件（实际使用）
├── config.example.json # 配置示例
├── package.json       # 依赖配置
└── README.md          # 使用说明
```

## 注意事项

1. **首次使用建议设置 `headless: false`**，观察脚本运行情况
2. 滑块验证码需要图像识别支持，如遇到问题可尝试调整参数
3. 登录成功后浏览器会保持打开，方便手动操作
4. 按 `Ctrl + C` 可安全退出

## 常见问题

### 找不到 Chrome 浏览器？

脚本会自动检测以下路径：
- `/usr/bin/google-chrome`
- `/usr/bin/chromium`
- `/usr/bin/chromium-browser`
- macOS Chrome 等

如需指定浏览器路径，可修改 `login.js` 中的 `findChromePath()` 方法。

### 滑块验证失败？

1. 检查网络连接
2. 尝试增加 `slowMo` 值
3. 开启 `debug: true` 查看截图分析原因

## License

MIT
