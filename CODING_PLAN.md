# Coding Plan 使用指南

> Pineapple 🍍 的代码开发工作流

---

## 配置概览

| 配置项 | 路径 | 说明 |
|--------|------|------|
| Claude 全局配置 | `~/.config/claude/config.json` | API 和基础设置 |
| Coding Plan | `~/.config/claude/coding-plan.json` | 工作流和代码规范 |
| 工作区设置 | `.claude/settings.json` | 项目特定配置 |
| 环境变量 | `.env` | API Key 等敏感信息 |

---

## 开发工作流 (5阶段)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  需求分析   │ →  │  代码编写   │ →  │  注释完善   │ →  │  测试验证   │ →  │  优化交付   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### 阶段1: 需求分析
- [ ] 明确功能目标
- [ ] 确认技术栈和约束
- [ ] 定义交付标准

### 阶段2: 代码编写
- [ ] 模块化设计
- [ ] 清晰的变量命名
- [ ] 合理的函数拆分

### 阶段3: 注释完善
- [ ] 函数/类文档
- [ ] 关键逻辑说明
- [ ] 复杂算法解释

### 阶段4: 测试验证
- [ ] 单元测试
- [ ] 集成测试
- [ ] 边界条件检查

### 阶段5: 优化交付
- [ ] 性能优化
- [ ] 可读性提升
- [ ] Git 提交推送

---

## 代码规范

### Python
- 格式化: `black`
- 检查: `pylint`
- 行宽: 88 字符
- 文档: Google Style

### JavaScript/TypeScript
- 格式化: `prettier`
- 检查: `eslint`
- 引号: 单引号
- 分号: 必须

### 通用
- 缩进: 2 空格
- 换行符: LF
- 文件末尾: 空行

---

## Git 提交规范

```
[type] description

类型:
- feat: 新功能
- fix: Bug 修复
- docs: 文档更新
- style: 代码格式
- refactor: 重构
- test: 测试相关
- chore: 构建/工具
```

---

## 快速开始

### 1. 配置 API Key
```bash
# 复制模板
cp .env.example .env

# 编辑 .env，填入你的阿里云百炼 API Key
nano .env
```

### 2. 验证配置
```bash
# 检查 Git 远程仓库
git remote -v

# 检查配置加载
claude config verify
```

### 3. 开始编码
直接告诉我你的需求，我会按照 Coding Plan 的 5 阶段流程为你完成代码开发。

---

## 学习记录

- **LEARNINGS.md** - 成功经验
- **ERRORS.md** - 错误记录
- **FEATURE_REQUESTS.md** - 功能请求

---

*配置时间: 2026-03-17*
*Agent: Pineapple 🍍*
