import chalk from 'chalk'
import type { Message } from '../types.js'

/**
 * 格式化 LLM 响应内容
 */
export function formatResponse(content: string): string {
  return content
}

/**
 * 渲染单条消息到控制台 — 统一渲染逻辑
 * 用于 renderHistory（resume 时）和 handleChat（实时聊天时）
 *
 * marker 宽度 = 4（"  ⏺ " = 2空格 + ⏺ + 1空格），续行缩进对齐
 */
const INDENT = '    '

export function renderMessage(msg: { role: string; content: string; timestamp?: string }): void {
  if (!msg.content) return

  // 压缩连续空行，去掉所有空行（保证行间无间距）
  const lines = msg.content.trim().split('\n').filter(l => l.trim() !== '')
  if (lines.length === 0) return

  if (msg.role === 'user') {
    const ts = msg.timestamp ? chalk.dim(`  ${msg.timestamp.slice(11, 19)}`) : ''
    console.log(chalk.cyan.bold('  \u276f ') + lines[0] + ts)
    for (let i = 1; i < lines.length; i++) {
      console.log(INDENT + lines[i])
    }
  } else if (msg.role === 'assistant') {
    console.log(chalk.green('  \u23fa ') + lines[0])
    for (let i = 1; i < lines.length; i++) {
      console.log(INDENT + lines[i])
    }
  } else if (msg.role === 'system') {
    console.log(chalk.dim('  [system] ') + lines[0])
    for (let i = 1; i < lines.length; i++) {
      console.log(INDENT + lines[i])
    }
  }
}

/**
 * 渲染消息历史到控制台（用于 /resume 和 /history）
 *
 * 间距规则：
 *   - 同一轮内行间：无空行
 *   - 问→答：1 空行
 *   - 答→下一问：2 空行
 */
export function renderHistory(messages: Message[]): void {
  let prevRole: string | null = null

  for (const msg of messages) {
    if (!msg.content) continue

    // 间距：答→问 = 2 空行（新轮），问→答 = 1 空行（同轮），首条 = 0
    if (prevRole !== null) {
      const gap = (prevRole === 'assistant' && msg.role === 'user') ? 2 : 1
      for (let i = 0; i < gap; i++) console.log()
    }

    renderMessage(msg)
    prevRole = msg.role
  }
}
