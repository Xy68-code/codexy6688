# HEARTBEAT.md - Pineapple🍍的定期检查任务

> 配置心跳任务，定期检查技能更新和学习记录

---

## 每周检查（技能更新）

```
Read HEARTBEAT.md if it exists.

每周技能检查：
1. 运行 `clawhub list` 查看已安装技能
2. 运行 `clawhub search` 搜索相关新技能（关键词：code, debug, optimize, claude）
3. 检查已安装技能是否有更新
4. 如有新技能或更新，向用户报告

如果无需操作，回复 HEARTBEAT_OK
```

---

## 每日记录（学习日志）

```
Read HEARTBEAT.md if it exists.

每日学习检查：
1. 检查是否有新的学习记录需要整理
2. 回顾最近7天的 LEARNINGS.md
3. 如有重要发现，更新 MEMORY.md

如果无需操作，回复 HEARTBEAT_OK
```

---

## 每月优化（流程改进）

```
Read HEARTBEAT.md if it exists.

每月优化检查：
1. 回顾本月所有学习记录
2. 总结成功经验和失败教训
3. 更新 AGENTS.md 中的最佳实践
4. 向用户报告进化成果

如果无需操作，回复 HEARTBEAT_OK
```

---

## 当前配置

| 检查类型 | 频率 | 状态 |
|----------|------|------|
| 技能检查 | 每周 | 待配置定时任务 |
| 学习记录 | 每日 | 待配置定时任务 |
| 流程优化 | 每月 | 待配置定时任务 |

---

*配置完成时间：2026-03-17*
