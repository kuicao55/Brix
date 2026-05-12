---
name: commit
description: 提交代码变更
whenToUse: 当用户要求提交代码、创建 commit、保存变更时使用
allowedTools:
  - Bash
  - Read
---

# Commit Skill

请按以下步骤提交代码：

1. 运行 `git status` 查看变更
2. 运行 `git diff` 查看具体修改
3. 分析变更性质，编写 commit message（中文，简洁描述改动）
4. 执行 `git add` 和 `git commit`

$ARGUMENTS
