import { describe, expect, it, mock, beforeEach, afterEach } from 'bun:test'

describe('Banner', () => {
  let consoleOutput: string[]
  let consoleSpy: ReturnType<typeof mock>

  beforeEach(() => {
    consoleOutput = []
    consoleSpy = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    console.log = consoleSpy
  })

  afterEach(() => {
    console.log = console.log
  })

  it('应该从 src/cli/banner.ts 导出 showBanner 函数', async () => {
    const { showBanner } = await import('../src/cli/banner.js')
    expect(showBanner).toBeDefined()
    expect(typeof showBanner).toBe('function')
  })

  it('应该输出 BRIX ASCII 艺术字', async () => {
    const { showBanner } = await import('../src/cli/banner.js')
    showBanner('claude-3', '0.1.0', '/home/user/project')
    // ASCII art 包含方块字符
    const output = consoleOutput.join('\n')
    expect(output).toContain('██████╗')
    expect(output).toContain('BRIX')
  })

  it('应该输出模型信息', async () => {
    const { showBanner } = await import('../src/cli/banner.js')
    showBanner('claude-3-sonnet', '0.1.0', '/tmp')
    const output = consoleOutput.join('\n')
    expect(output).toContain('claude-3-sonnet')
  })

  it('应该输出版本信息', async () => {
    const { showBanner } = await import('../src/cli/banner.js')
    showBanner('model', '1.2.3', '/tmp')
    const output = consoleOutput.join('\n')
    expect(output).toContain('1.2.3')
  })

  it('应该输出工作目录信息', async () => {
    const { showBanner } = await import('../src/cli/banner.js')
    showBanner('model', '0.1.0', '/Users/test/project')
    const output = consoleOutput.join('\n')
    expect(output).toContain('/Users/test/project')
  })

  it('应该输出帮助提示', async () => {
    const { showBanner } = await import('../src/cli/banner.js')
    showBanner('model', '0.1.0', '/tmp')
    const output = consoleOutput.join('\n')
    expect(output).toContain('/help')
    expect(output).toContain('Ctrl+C')
  })

  it('应该调用 console.log 多次输出完整横幅', async () => {
    const { showBanner } = await import('../src/cli/banner.js')
    showBanner('model', '0.1.0', '/tmp')
    // banner 至少调用 5 次 console.log
    expect(consoleSpy.mock.calls.length).toBeGreaterThanOrEqual(5)
  })
})

describe('Spinner', () => {
  let stdoutWrite: ReturnType<typeof mock>
  let stdoutOutput: string[]

  beforeEach(() => {
    stdoutOutput = []
    stdoutWrite = mock((chunk: string) => {
      stdoutOutput.push(chunk)
      return true
    })
    process.stdout.write = stdoutWrite as any
  })

  afterEach(() => {
    process.stdout.write = process.stdout.write
  })

  it('应该从 src/cli/spinner.ts 导出 Spinner 类', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    expect(Spinner).toBeDefined()
    expect(typeof Spinner).toBe('function')
  })

  it('应该使用默认标签创建实例', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner()
    expect(spinner).toBeDefined()
  })

  it('应该使用自定义标签创建实例', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner('Loading...')
    expect(spinner).toBeDefined()
  })

  it('start() 应该开始动画并写入 stdout', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner('Testing...')
    spinner.start()
    // 等待至少一帧
    await new Promise((r) => setTimeout(r, 150))
    expect(stdoutOutput.length).toBeGreaterThan(0)
    expect(stdoutOutput.some((s) => s.includes('Testing...'))).toBe(true)
    spinner.stop()
  })

  it('start() 应该包含 Braille 字符', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner()
    spinner.start()
    await new Promise((r) => setTimeout(r, 150))
    const brailleChars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    const hasBraille = stdoutOutput.some((s) =>
      brailleChars.some((b) => s.includes(b))
    )
    expect(hasBraille).toBe(true)
    spinner.stop()
  })

  it('stop() 应该停止动画并清除行', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner()
    spinner.start()
    await new Promise((r) => setTimeout(r, 150))
    stdoutOutput.length = 0
    spinner.stop()
    // stop 会写入清除行的内容
    expect(stdoutOutput.some((s) => s.includes('\r'))).toBe(true)
  })

  it('updateLabel() 应该更新标签', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner('Old label')
    spinner.start()
    await new Promise((r) => setTimeout(r, 150))
    spinner.updateLabel('New label')
    stdoutOutput.length = 0
    await new Promise((r) => setTimeout(r, 150))
    expect(stdoutOutput.some((s) => s.includes('New label'))).toBe(true)
    spinner.stop()
  })

  it('finish() 应该输出完成信息', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner()
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    spinner.start()
    await new Promise((r) => setTimeout(r, 50))
    spinner.finish('Complete!')
    expect(consoleOutput.some((s) => s.includes('Complete!'))).toBe(true)
    expect(consoleOutput.some((s) => s.includes('✓'))).toBe(true)
    console.log = originalLog
  })

  it('finish() 应该使用默认标签 Done', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner()
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    spinner.start()
    await new Promise((r) => setTimeout(r, 50))
    spinner.finish()
    expect(consoleOutput.some((s) => s.includes('Done'))).toBe(true)
    console.log = originalLog
  })

  it('fail() 应该输出失败信息', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner()
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    spinner.start()
    await new Promise((r) => setTimeout(r, 50))
    spinner.fail('Error occurred')
    expect(consoleOutput.some((s) => s.includes('Error occurred'))).toBe(true)
    expect(consoleOutput.some((s) => s.includes('✗'))).toBe(true)
    console.log = originalLog
  })

  it('fail() 应该使用默认标签 Failed', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner()
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    spinner.start()
    await new Promise((r) => setTimeout(r, 50))
    spinner.fail()
    expect(consoleOutput.some((s) => s.includes('Failed'))).toBe(true)
    console.log = originalLog
  })

  it('应该在动画帧中显示经过时间', async () => {
    const { Spinner } = await import('../src/cli/spinner.js')
    const spinner = new Spinner('Timed')
    spinner.start()
    await new Promise((r) => setTimeout(r, 250))
    // 应该包含秒数显示 (如 "0.1s", "0.2s" 等)
    expect(stdoutOutput.some((s) => /[\d.]+s/.test(s))).toBe(true)
    spinner.stop()
  })
})

describe('StageIndicator', () => {
  let stdoutWrite: ReturnType<typeof mock>
  let stdoutOutput: string[]

  beforeEach(() => {
    stdoutOutput = []
    stdoutWrite = mock((chunk: string) => {
      stdoutOutput.push(chunk)
      return true
    })
    process.stdout.write = stdoutWrite as any
  })

  afterEach(() => {
    process.stdout.write = process.stdout.write
  })

  it('应该从 src/cli/stage-indicator.ts 导出 StageIndicator 类', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    expect(StageIndicator).toBeDefined()
    expect(typeof StageIndicator).toBe('function')
  })

  it('应该使用默认标签创建实例', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    expect(indicator).toBeDefined()
    indicator.finish()
  })

  it('应该使用自定义标签创建实例', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator('Processing...')
    expect(indicator).toBeDefined()
    indicator.finish()
  })

  it('构造时应自动启动 spinner', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator('Test...')
    await new Promise((r) => setTimeout(r, 150))
    expect(stdoutOutput.length).toBeGreaterThan(0)
    indicator.finish()
  })

  it('update() 应该更新为已知阶段标签', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 100))
    indicator.update('Memory')
    stdoutOutput.length = 0
    await new Promise((r) => setTimeout(r, 150))
    expect(stdoutOutput.some((s) => s.includes('Loading memory...'))).toBe(true)
    indicator.finish()
  })

  it('update() 应该将未知阶段映射为 Working...', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 100))
    indicator.update('UnknownStage')
    stdoutOutput.length = 0
    await new Promise((r) => setTimeout(r, 150))
    expect(stdoutOutput.some((s) => s.includes('Working...'))).toBe(true)
    indicator.finish()
  })

  it('finish() 应该停止 spinner 并防止后续 update', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 100))
    indicator.finish()
    stdoutOutput.length = 0
    // finish 后 update 不应产生输出
    indicator.update('Route')
    await new Promise((r) => setTimeout(r, 150))
    expect(stdoutOutput.length).toBe(0)
  })

  it('stop_silent() 应该停止 spinner 而不输出完成信息', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 100))
    indicator.stop_silent()
    // stop_silent 不应输出完成信息
    expect(consoleOutput.some((s) => s.includes('Done'))).toBe(false)
    expect(consoleOutput.some((s) => s.includes('✓'))).toBe(false)
    console.log = originalLog
  })

  it('所有 STAGE_LABELS 阶段应该正确映射', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const stages: [string, string][] = [
      ['Memory', 'Loading memory...'],
      ['Intent', 'Classifying intent...'],
      ['Complexity', 'Evaluating complexity...'],
      ['Route', 'Selecting model...'],
      ['Planning', 'Planning...'],
    ]
    for (const [stage, expectedLabel] of stages) {
      const indicator = new StageIndicator()
      await new Promise((r) => setTimeout(r, 50))
      indicator.update(stage)
      stdoutOutput.length = 0
      await new Promise((r) => setTimeout(r, 150))
      expect(stdoutOutput.some((s) => s.includes(expectedLabel))).toBe(true)
      indicator.finish()
    }
  })

  it('重复调用 finish() 不应报错', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 50))
    indicator.finish()
    // 第二次调用不应抛出异常
    expect(() => indicator.finish()).not.toThrow()
  })

  it('重复调用 stop_silent() 不应报错', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 50))
    indicator.stop_silent()
    expect(() => indicator.stop_silent()).not.toThrow()
  })
})
