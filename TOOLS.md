# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Preferred code editors
- SSH hosts for deployment
- API keys for testing
- Database connections
- Anything environment-specific

## Examples

```markdown
### Development Environment

- Editor: VS Code
- Terminal: bash
- Python version: 3.11+

### SSH

- dev-server → 192.168.1.100, user: deploy
- prod-server → production.example.com, user: admin

### API Testing

- Postman collections location
- Test environment endpoints
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

### 🔒 技能安全检查 (skill-vetter)
**安装任何技能前必须执行安全检查！**

```bash
# 1. 搜索技能
clawhub search <skill-name>

# 2. 安全检查 (阅读 SKILL.md)
cat ~/.agents/workspaces/pineapple/skills/<skill-name>/SKILL.md

# 3. 检查 RED FLAGS:
#    • curl/wget 到未知 URL
#    • 发送数据到外部服务器
#    • 请求凭证/令牌/API key
#    • 读取 ~/.ssh, ~/.aws, ~/.config
#    • 访问 MEMORY.md, USER.md, SOUL.md
#    • 使用 eval() 或 exec() 执行外部输入
#    • 混淆或压缩的代码

# 4. 评估风险等级
#    🟢 LOW - 笔记、天气、格式化
#    🟡 MEDIUM - 文件操作、浏览器、API
#    🔴 HIGH - 凭证、交易、系统
#    ⛔ EXTREME - 安全配置、root 权限

# 5. 安装 (仅当安全检查通过后)
clawhub install <skill-id>
```

---

Add whatever helps you do your job. This is your cheat sheet.
