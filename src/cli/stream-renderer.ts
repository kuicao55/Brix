import chalk from 'chalk'
import { marked } from 'marked'
// @ts-ignore — marked-terminal 没有类型声明
import TerminalRenderer from 'marked-terminal'

// 配置 marked 使用 terminal renderer
marked.setOptions({ renderer: new TerminalRenderer() } as any)

const BRAILLE_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

export class StreamRenderer {
  private pending: string = ''
  private rendered: string = ''
  private marker: string
  private lastDeltaTime: number = 0
  private activityTimer: ReturnType<typeof setTimeout> | null = null
  private indicatorFrame: number = 0
  private indicatorLabel: string = 'Waiting for tool call...'

  constructor(marker: string = chalk.green('  ⏺ ')) {
    this.marker = marker
  }

  pushDelta(delta: string): void {
    this.lastDeltaTime = Date.now()
    this.pending += delta

    // 查找安全边界
    const boundary = this.findSafeBoundary(this.pending)
    if (boundary !== null) {
      this.rendered += this.pending.slice(0, boundary)
      this.pending = this.pending.slice(boundary)
      this.updateDisplay()
    }

    // 重置 activity indicator
    this.resetActivityIndicator()
  }

  private findSafeBoundary(text: string): number | null {
    // 在代码块结束后
    const codeFenceEnd = text.lastIndexOf('```')
    if (codeFenceEnd > 0 && codeFenceEnd < text.length - 3) {
      const afterFence = text.indexOf('\n', codeFenceEnd + 3)
      if (afterFence !== -1) return afterFence + 1
    }

    // 在空行后
    const lastBlankLine = text.lastIndexOf('\n\n')
    if (lastBlankLine !== -1) return lastBlankLine + 2

    // 在非代码块的换行后
    const lastNewline = text.lastIndexOf('\n')
    if (lastNewline !== -1) return lastNewline + 1

    return null
  }

  private updateDisplay(): void {
    if (this.rendered) {
      const output = marked(this.rendered)
      process.stdout.write(this.marker + output)
    }
  }

  private resetActivityIndicator(): void {
    if (this.activityTimer) {
      clearTimeout(this.activityTimer)
    }
    this.activityTimer = setTimeout(() => {
      this.showActivityIndicator()
    }, 800)
  }

  private showActivityIndicator(): void {
    const frame = BRAILLE_FRAMES[this.indicatorFrame % BRAILLE_FRAMES.length]
    process.stdout.write(`\r  ${chalk.dim(frame)} ${chalk.dim(this.indicatorLabel)}`)
    this.indicatorFrame++
    this.activityTimer = setTimeout(() => this.showActivityIndicator(), 100)
  }

  flush(): void {
    if (this.activityTimer) {
      clearTimeout(this.activityTimer)
      this.activityTimer = null
    }
    // 清除 activity indicator
    process.stdout.write('\r' + ' '.repeat(80) + '\r')

    if (this.pending) {
      this.rendered += this.pending
      this.pending = ''
      this.updateDisplay()
    }
  }

  getOutput(): string {
    return this.rendered
  }
}
