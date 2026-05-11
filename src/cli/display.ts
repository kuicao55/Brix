import chalk from 'chalk'
import type { Message } from '../types.js'

/**
 * 格式化 LLM 响应内容
 */
export function formatResponse(content: string): string {
  return content
}

/**
 * 渲染消息历史到控制台
 */
export function renderHistory(messages: Message[]): void {
  for (const msg of messages) {
    if (msg.role === 'user') {
      console.log(chalk.cyan.bold('  \u276f ') + msg.content)
      console.log()
    } else if (msg.role === 'assistant') {
      console.log(chalk.green('  \u23fa ') + msg.content)
      console.log()
    } else if (msg.role === 'system') {
      console.log(chalk.dim('  [system] ') + msg.content)
      console.log()
    }
    // tool 消息：完全跳过（无输出、无空行）
  }
}
