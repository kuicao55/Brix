/**
 * 命令定义 — REPL 斜杠命令列表
 */

export const COMMANDS: Array<[string, string]> = [
  ['/help', '显示所有可用命令'],
  ['/quit', '保存会话并退出（也可用 /exit）'],
  ['/clear', '创建新会话'],
  ['/model', '查看当前默认模型'],
  ['/history', '查看当前会话的消息历史'],
  ['/resume [id]', '恢复历史会话（交互式选择或按 ID 前缀）'],
  ['/soul', '查看 soul.md 记忆文件'],
  ['/user', '查看 user.md 记忆文件'],
  ['/log', '交互式日志查看器'],
]
