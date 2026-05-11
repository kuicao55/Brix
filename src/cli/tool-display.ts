import chalk from 'chalk'
import { Spinner } from './spinner.js'

/** 工具图标映射 */
const TOOL_ICONS: Record<string, string> = {
  bash: '⚡',
  file_read: '📄',
  file_write: '✏️',
  file_edit: '📝',
  web_search: '🔍',
  calculator: '🧮',
  weather: '🌤️',
}

/**
 * ToolDisplay - 工具调用面板显示
 * 展示工具调用的开始、结果，以及中间的 thinking spinner
 */
export class ToolDisplay {
  private activeSpinner: Spinner | null = null

  /** 显示工具调用开始面板 */
  showToolStart(toolName: string, toolInput: Record<string, unknown>): void {
    this.stopThinking()
    const icon = TOOL_ICONS[toolName] || '🔧'
    const detail = this.formatDetail(toolName, toolInput)

    console.log(chalk.dim('  ⏺ Calling tools...'))
    console.log(chalk.gray('┌─ ') + chalk.bold.cyan(`${icon} ${toolName}`) + chalk.gray(' ─'))
    console.log(chalk.gray('│ ') + detail)
    console.log(chalk.gray('└─' + '─'.repeat(40)))
  }

  /** 显示工具调用结果（单行摘要） */
  showToolResult(
    toolName: string,
    result: string,
    elapsedMs: number,
    isError: boolean = false,
  ): void {
    result = result ?? ''
    this.stopThinking()
    const icon = TOOL_ICONS[toolName] || '🔧'
    const statusIcon = isError ? chalk.red('✗') : chalk.green('✓')
    const elapsed = chalk.dim.cyan(`${elapsedMs.toFixed(0)}ms`)

    const preview = result.slice(0, 200).replace(/\n/g, ' ')
    const truncated = result.length > 200 ? '...' : ''

    let line = `  ⎯ ${chalk.dim(icon)} ${chalk.bold.cyan(toolName)} ${statusIcon} ${elapsed}`
    if (isError) {
      line += `  ${chalk.red(preview + truncated)}`
    }
    console.log(line)
    this.startThinking()
  }

  /** 启动 thinking spinner（幂等） */
  startThinking(): void {
    if (!this.activeSpinner) {
      this.activeSpinner = new Spinner('Thinking...')
      this.activeSpinner.start()
    }
  }

  /** 停止 thinking spinner（幂等） */
  stopThinking(): void {
    if (this.activeSpinner) {
      this.activeSpinner.stop()
      this.activeSpinner = null
    }
  }

  /** 清理资源 */
  cleanup(): void {
    this.stopThinking()
  }

  /** 格式化工具详情行 */
  private formatDetail(toolName: string, toolInput: Record<string, unknown>): string {
    if (!toolInput || typeof toolInput !== 'object') {
      return chalk.dim(JSON.stringify(toolInput).slice(0, 150))
    }

    switch (toolName) {
      case 'bash':
        return chalk.white.bgGray(` $ ${toolInput.command || ''} `)
      case 'file_read':
        return `📄 Reading ${toolInput.path || ''}`
      case 'file_write':
        return `✏️ Writing ${toolInput.path || ''} (${String(toolInput.content ?? '').split('\n').length} lines)`
      case 'file_edit':
        return `📝 Editing ${toolInput.path || ''}`
      case 'web_search':
        return `🔍 Searching: ${toolInput.query || ''}`
      default:
        return chalk.dim(JSON.stringify(toolInput).slice(0, 150))
    }
  }
}
