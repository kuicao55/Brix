import chalk from 'chalk'

const BRAILLE_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

export class Spinner {
  private label: string
  private frameIdx: number = 0
  private startTime: number = 0
  private running: boolean = false
  private timer: ReturnType<typeof setInterval> | null = null

  constructor(label: string = 'Thinking...') {
    this.label = label
  }

  private renderFrame(): string {
    const elapsed = (Date.now() - this.startTime) / 1000
    const frame = BRAILLE_FRAMES[this.frameIdx % BRAILLE_FRAMES.length]
    return `  ${chalk.blue(frame)} ${chalk.dim(this.label)}  ${chalk.dim.cyan(elapsed.toFixed(1) + 's')}`
  }

  start(): void {
    this.running = true
    this.startTime = Date.now()
    this.timer = setInterval(() => {
      this.frameIdx++
      process.stdout.write('\r' + this.renderFrame())
    }, 100)
  }

  stop(): void {
    this.running = false
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
    // 用 ANSI 转义码清除整行
    process.stdout.write('\r\x1B[2K')
  }

  updateLabel(label: string): void {
    this.label = label
  }

  finish(label: string = 'Done'): void {
    this.stop()
    const elapsed = (Date.now() - this.startTime) / 1000
    console.log(`  ${chalk.green('✓')} ${label}  ${chalk.dim(elapsed.toFixed(1) + 's')}`)
  }

  fail(label: string = 'Failed'): void {
    this.stop()
    const elapsed = (Date.now() - this.startTime) / 1000
    console.log(`  ${chalk.red('✗')} ${label}  ${chalk.dim(elapsed.toFixed(1) + 's')}`)
  }
}
