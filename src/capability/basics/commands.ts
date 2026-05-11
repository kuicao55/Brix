/**
 * 命令定义 — REPL 斜杠命令列表
 */

export const COMMANDS: Array<[string, string]> = [
  ['/help', 'Show help message'],
  ['/quit', 'Exit REPL'],
  ['/clear', 'Clear current session'],
  ['/model', 'Show/switch current model'],
  ['/history', 'Show message history'],
  ['/resume [id]', 'Resume a session'],
  ['/soul', 'Show soul.md content'],
  ['/user', 'Show user.md content'],
  ['/log', 'Show FlowLog entries'],
]
