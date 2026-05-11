import chalk from 'chalk'
import { Marked } from 'marked'
// @ts-ignore — marked-terminal 没有类型声明
import TerminalRenderer from 'marked-terminal'

// 使用独立的 marked 实例，避免污染全局状态
const markedInstance = new Marked()
markedInstance.setOptions({ renderer: new TerminalRenderer() } as any)

const BRAILLE_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

export class StreamRenderer {
  private pending: string = ''
  private rendered: string = ''
  private marker: string
  private markerWritten: boolean = false
  private lastRenderedIndex: number = 0
  private activityTimer: ReturnType<typeof setTimeout> | null = null
  private indicatorFrame: number = 0
  private indicatorLabel: string = 'Waiting for tool call...'

  constructor(marker: string = chalk.green('  ⏺ ')) {
    this.marker = marker
  }

  pushDelta(delta: string): void {
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
    // 统计代码围栏数量 — 如果为奇数，说明在代码块内部，不应切割
    const fenceCount = (text.match(/```/g) || []).length
    if (fenceCount % 2 !== 0) return null // 在代码块内部，不安全

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
    const newContent = this.rendered.slice(this.lastRenderedIndex)
    if (newContent) {
      const output = markedInstance.parse(newContent) as string
      const prefix = this.markerWritten ? '' : this.marker
      this.markerWritten = true
      process.stdout.write(prefix + output)
      this.lastRenderedIndex = this.rendered.length
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
    process.stdout.write(`\r\x1B[2K  ${chalk.dim(frame)} ${chalk.dim(this.indicatorLabel)}`)
    this.indicatorFrame++
    this.activityTimer = setTimeout(() => this.showActivityIndicator(), 100)
  }

  flush(): void {
    if (this.activityTimer) {
      clearTimeout(this.activityTimer)
      this.activityTimer = null
    }
    // 清除 activity indicator
    process.stdout.write('\r\x1B[2K')

    if (this.pending) {
      this.rendered += this.pending
      this.pending = ''
      this.updateDisplay()
    }
  }

  getOutput(): string {
    return this.rendered
  }

  dispose(): void {
    if (this.activityTimer) {
      clearTimeout(this.activityTimer)
      this.activityTimer = null
    }
  }
}
