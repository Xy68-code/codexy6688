# AP SMS 自动登录脚本

AP SMS 系统的自动化登录工具，支持滑块验证码识别。

## 功能特性

- ✅ 自动打开登录页面
- ✅ 智能识别滑块验证码
- ✅ 模拟人类滑动轨迹
- ✅ 自动填写账号密码
- ✅ 支持无头模式运行
- ✅ 详细的调试日志

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本用法

```bash
python auto_login.py --username YOUR_USERNAME --password YOUR_PASSWORD
```

### 参数说明

| 参数 | 简写 | 说明 |
|------|------|------|
| `--username` | `-u` | 登录用户名（必填） |
| `--password` | `-p` | 登录密码（必填） |
| `--headless` | - | 无头模式（不显示浏览器窗口） |
| `--debug` | `-d` | 开启调试输出 |
| `--keep-open` | - | 登录成功后保持浏览器打开 |

### 使用示例

```bash
# 正常模式（可见浏览器窗口）
python auto_login.py -u admin -p 123456

# 无头模式（后台运行）
python auto_login.py -u admin -p 123456 --headless

# 开启调试输出
python auto_login.py -u admin -p 123456 -d

# 登录成功后保持浏览器打开
python auto_login.py -u admin -p 123456 --keep-open
```

## 项目结构

```
ap_sms_login/
├── auto_login.py      # 主程序
├── slider_solver.py   # 滑块验证码识别模块
├── requirements.txt   # 依赖列表
└── README.md         # 使用说明
```

## 滑块识别原理

1. **图像处理**: 使用 OpenCV 进行边缘检测
2. **缺口定位**: 通过轮廓分析找到缺口位置
3. **轨迹模拟**: 生成加速-减速的自然滑动轨迹
4. **人机模拟**: 添加随机偏移和时间间隔

## 注意事项

1. **Chrome 浏览器**: 需要安装 Chrome 浏览器
2. **网络环境**: 确保能正常访问目标网站
3. **验证码刷新**: 如果识别失败会自动重试
4. **元素选择器**: 如果网站更新可能需要调整选择器

## 自定义配置

如果网站结构变化，可以修改 `auto_login.py` 中的选择器：

```python
# 用户名输入框选择器
username_selectors = [
    "#username",
    "input[name='username']",
    # 添加新的选择器
]

# 滑块验证码选择器
selectors = [
    (".ap-slider-bg", ".ap-slider-block", ".ap-slider-track"),
    # 添加新的选择器
]
```

## 许可证

仅供学习研究使用。
