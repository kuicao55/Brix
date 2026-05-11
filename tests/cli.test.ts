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

  it('fail() 方法应该存在', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    expect(typeof indicator.fail).toBe('function')
    indicator.fail()
  })

  it('fail() 应该输出失败信息和红色标记', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 50))
    indicator.fail('Connection timeout')
    expect(consoleOutput.some((s) => s.includes('Connection timeout'))).toBe(true)
    expect(consoleOutput.some((s) => s.includes('✗'))).toBe(true)
    console.log = originalLog
  })

  it('fail() 应该使用默认标签 Error', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 50))
    indicator.fail()
    expect(consoleOutput.some((s) => s.includes('Error'))).toBe(true)
    console.log = originalLog
  })

  it('重复调用 fail() 不应报错', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 50))
    indicator.fail()
    expect(() => indicator.fail()).not.toThrow()
  })

  it('fail() 后 update() 不应产生输出', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 100))
    indicator.fail()
    stdoutOutput.length = 0
    indicator.update('Route')
    await new Promise((r) => setTimeout(r, 150))
    expect(stdoutOutput.length).toBe(0)
  })

  it('finish() 应该输出绿色完成标记', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 50))
    indicator.finish()
    expect(consoleOutput.some((s) => s.includes('✓'))).toBe(true)
    console.log = originalLog
  })

  it('stop_silent() 不应该输出任何完成标记', async () => {
    const { StageIndicator } = await import('../src/cli/stage-indicator.js')
    const consoleOutput: string[] = []
    const originalLog = console.log
    console.log = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    const indicator = new StageIndicator()
    await new Promise((r) => setTimeout(r, 50))
    indicator.stop_silent()
    expect(consoleOutput.some((s) => s.includes('✓'))).toBe(false)
    expect(consoleOutput.some((s) => s.includes('Done'))).toBe(false)
    console.log = originalLog
  })
})

describe('StreamRenderer', () => {
  let stdoutWrite: ReturnType<typeof mock>
  let stdoutOutput: string[]

  beforeEach(() => {
    stdoutOutput = []
    stdoutWrite = mock((chunk: string | Uint8Array) => {
      stdoutOutput.push(typeof chunk === 'string' ? chunk : new TextDecoder().decode(chunk))
      return true
    })
    process.stdout.write = stdoutWrite as any
  })

  afterEach(() => {
    process.stdout.write = process.stdout.write
  })

  it('应该从 src/cli/stream-renderer.ts 导出 StreamRenderer 类', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    expect(StreamRenderer).toBeDefined()
    expect(typeof StreamRenderer).toBe('function')
  })

  it('应该使用默认 marker 创建实例', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer()
    expect(renderer).toBeDefined()
  })

  it('应该使用自定义 marker 创建实例', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('  > ')
    expect(renderer).toBeDefined()
  })

  it('pushDelta 应该在换行边界处渲染内容', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('Hello')
    // 还没有换行，不应渲染
    expect(renderer.getOutput()).toBe('')
    renderer.pushDelta(' World\n')
    // 换行后应渲染
    expect(renderer.getOutput()).toContain('Hello World')
    renderer.flush()
  })

  it('pushDelta 应该在双换行边界处渲染段落', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('段落一。\n\n')
    expect(renderer.getOutput()).toContain('段落一')
    renderer.flush()
  })

  it('pushDelta 应该累积 pending 直到安全边界', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('part1 ')
    renderer.pushDelta('part2 ')
    // 没有换行，不应渲染
    expect(renderer.getOutput()).toBe('')
    renderer.pushDelta('part3\n')
    // 换行后应渲染全部
    const output = renderer.getOutput()
    expect(output).toContain('part1')
    expect(output).toContain('part2')
    expect(output).toContain('part3')
    renderer.flush()
  })

  it('flush() 应该渲染所有 pending 内容', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('未完成的文本')
    // 没有边界，getOutput 应为空
    expect(renderer.getOutput()).toBe('')
    renderer.flush()
    // flush 后应包含所有内容
    expect(renderer.getOutput()).toContain('未完成的文本')
  })

  it('flush() 在无 pending 内容时不应报错', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    // 没有 pushDelta，直接 flush
    expect(() => renderer.flush()).not.toThrow()
    expect(renderer.getOutput()).toBe('')
  })

  it('getOutput() 应该返回已渲染的纯文本内容', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('测试内容\n')
    const output = renderer.getOutput()
    expect(output).toContain('测试内容')
    renderer.flush()
  })

  it('pushDelta 应该在代码块结束后渲染', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('代码如下：\n\n```python\nprint("hello")\n```\n')
    const output = renderer.getOutput()
    expect(output).toContain('print')
    renderer.flush()
  })

  it('多次 pushDelta 应该累积渲染结果', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('第一行\n')
    const afterFirst = renderer.getOutput()
    expect(afterFirst).toContain('第一行')

    renderer.pushDelta('第二行\n')
    const afterSecond = renderer.getOutput()
    expect(afterSecond).toContain('第一行')
    expect(afterSecond).toContain('第二行')
    renderer.flush()
  })

  it('pushDelta 应该写入 stdout', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('输出测试\n')
    expect(stdoutOutput.length).toBeGreaterThan(0)
    renderer.flush()
  })

  it('应该在 0.8s 空闲后显示 activity indicator', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('some text')
    // 等待 activity indicator 出现 (> 800ms)
    await new Promise((r) => setTimeout(r, 950))
    // 应该有 braille 字符输出
    const brailleChars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    const hasBraille = stdoutOutput.some((s) =>
      brailleChars.some((b) => s.includes(b))
    )
    expect(hasBraille).toBe(true)
    renderer.flush()
  })

  it('新的 pushDelta 应该重置 activity indicator', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('text')
    // 等待接近阈值
    await new Promise((r) => setTimeout(r, 600))
    // 新的 delta 应重置计时器
    renderer.pushDelta(' more\n')
    stdoutOutput.length = 0
    // 短暂等待 — 不应出现 indicator（因为刚重置）
    await new Promise((r) => setTimeout(r, 400))
    const brailleChars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    const hasBraille = stdoutOutput.some((s) =>
      brailleChars.some((b) => s.includes(b))
    )
    expect(hasBraille).toBe(false)
    renderer.flush()
  })

  it('flush() 应该清除 activity indicator', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('text')
    await new Promise((r) => setTimeout(r, 950))
    stdoutOutput.length = 0
    renderer.flush()
    // flush 后应有清除行的输出
    expect(stdoutOutput.some((s) => s.includes('\r'))).toBe(true)
  })

  it('默认 marker 应包含绿色圆点', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer()
    renderer.pushDelta('test\n')
    // stdout 输出中应包含 marker 字符
    const allOutput = stdoutOutput.join('')
    expect(allOutput).toContain('⏺')
    renderer.flush()
  })

  // ===== CRITICAL FIX TESTS =====

  it('pushDelta 多次边界不应重复输出到 stdout（CRITICAL）', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    // 推送第一段内容，触发渲染
    renderer.pushDelta('Hello World\n')
    // 推送第二段内容，触发第二次渲染
    renderer.pushDelta('Second Line\n')

    // 统计 "Hello World" 在 stdout 中出现的次数
    // 修复前：updateDisplay() 重新渲染整个 buffer，"Hello World" 会出现两次
    // 修复后：只渲染新增内容，"Hello World" 只出现一次
    const allOutput = stdoutOutput.join('')
    const helloMatches = allOutput.match(/Hello World/g) || []
    expect(helloMatches.length).toBe(1)

    renderer.flush()
  })

  it('pushDelta 三次边界不应重复输出任何内容到 stdout（CRITICAL）', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('Line A\n')
    renderer.pushDelta('Line B\n')
    renderer.pushDelta('Line C\n')

    const allOutput = stdoutOutput.join('')
    // 每行只应出现一次
    expect((allOutput.match(/Line A/g) || []).length).toBe(1)
    expect((allOutput.match(/Line B/g) || []).length).toBe(1)
    expect((allOutput.match(/Line C/g) || []).length).toBe(1)

    renderer.flush()
  })

  it('findSafeBoundary 在未闭合代码块内应返回 null（HIGH）', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    // 推送一个未闭合的代码块（只有开始 ```，没有结束 ```）
    // 当前 bug：lastIndexOf('```') 找到开头的 ```，在 ``` 后面找到换行就认为是安全边界
    // 修复后：检测到奇数个 ```，在代码块内部，不应找到安全边界
    renderer.pushDelta('一些文本\n\n```python\nprint("hello")\nmore code\n')
    // 修复后：未闭合代码块内不应找到安全边界，rendered 应为空
    const output = renderer.getOutput()
    // 未闭合代码块时，不应该渲染任何内容
    // 注意：修复前这个测试会失败，因为当前代码会在开头发 ``` 后找到边界
    expect(output).toBe('')
    renderer.flush()
  })

  it('findSafeBoundary 在闭合代码块后应正常找到边界', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    // 推送一个完整的代码块（偶数个 ```，应找到安全边界）
    renderer.pushDelta('一些文本\n\n```python\nprint("hello")\n```\n')
    const output = renderer.getOutput()
    // 闭合的代码块应该被渲染
    expect(output).toContain('print')
    renderer.flush()
  })

  it('flush() 应该渲染所有剩余 pending 内容', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    // 推送没有边界的内容
    renderer.pushDelta('pending content')
    // 没有边界，不应渲染
    expect(renderer.getOutput()).toBe('')
    // stdout 也不应有内容
    const outputBefore = stdoutOutput.join('')
    expect(outputBefore).not.toContain('pending content')
    // flush 应该渲染剩余内容
    renderer.flush()
    expect(renderer.getOutput()).toContain('pending content')
  })

  it('flush() 应该写入 pending 内容到 stdout', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('flush stdout test')
    stdoutOutput.length = 0
    renderer.flush()
    const allOutput = stdoutOutput.join('')
    expect(allOutput).toContain('flush stdout test')
  })

  it('dispose() 方法应该存在（LOW）', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    expect(typeof renderer.dispose).toBe('function')
  })

  it('dispose() 应该清理活动指示器定时器（LOW）', async () => {
    const { StreamRenderer } = await import('../src/cli/stream-renderer.js')
    const renderer = new StreamRenderer('')
    renderer.pushDelta('text')
    // dispose 应该清理定时器而不抛出异常
    expect(() => renderer.dispose()).not.toThrow()
    // dispose 后不应有定时器活动
    stdoutOutput.length = 0
    await new Promise((r) => setTimeout(r, 950))
    const brailleChars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    const hasBraille = stdoutOutput.some((s) =>
      brailleChars.some((b) => s.includes(b))
    )
    expect(hasBraille).toBe(false)
  })
})

describe('ToolDisplay', () => {
  let consoleOutput: string[]
  let consoleSpy: ReturnType<typeof mock>
  let originalStdoutWrite: typeof process.stdout.write

  beforeEach(() => {
    originalStdoutWrite = process.stdout.write
    consoleOutput = []
    consoleSpy = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    console.log = consoleSpy
  })

  afterEach(() => {
    console.log = console.log
    process.stdout.write = originalStdoutWrite
  })

  it('应该从 src/cli/tool-display.ts 导出 ToolDisplay 类', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    expect(ToolDisplay).toBeDefined()
    expect(typeof ToolDisplay).toBe('function')
  })

  it('应该创建 ToolDisplay 实例', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    expect(display).toBeDefined()
  })

  it('showToolStart 应该输出工具调用面板', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolStart('bash', { command: 'echo hello' })
    const output = consoleOutput.join('\n')
    expect(output).toContain('bash')
    expect(output).toContain('Calling tools')
    // 面板边框
    expect(output).toContain('┌─')
    expect(output).toContain('└─')
  })

  it('showToolStart 应该显示已知工具的图标', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolStart('bash', { command: 'ls' })
    const output = consoleOutput.join('\n')
    // bash 工具应该有闪电图标
    expect(output).toContain('⚡')
  })

  it('showToolStart 应该显示 file_read 工具的图标和路径', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolStart('file_read', { path: '/tmp/test.txt' })
    const output = consoleOutput.join('\n')
    expect(output).toContain('📄')
    expect(output).toContain('/tmp/test.txt')
  })

  it('showToolStart 应该显示 file_write 工具的图标和路径', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolStart('file_write', { path: '/tmp/out.txt', content: 'line1\nline2' })
    const output = consoleOutput.join('\n')
    expect(output).toContain('✏️')
    expect(output).toContain('/tmp/out.txt')
  })

  it('showToolStart 应该显示 file_edit 工具的图标和路径', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolStart('file_edit', { path: '/tmp/code.ts' })
    const output = consoleOutput.join('\n')
    expect(output).toContain('📝')
    expect(output).toContain('/tmp/code.ts')
  })

  it('showToolStart 应该显示 web_search 工具的查询内容', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolStart('web_search', { query: 'TypeScript tips' })
    const output = consoleOutput.join('\n')
    expect(output).toContain('🔍')
    expect(output).toContain('TypeScript tips')
  })

  it('showToolStart 应该为未知工具使用默认图标', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolStart('custom_tool', { foo: 'bar' })
    const output = consoleOutput.join('\n')
    expect(output).toContain('🔧')
    expect(output).toContain('custom_tool')
  })

  it('showToolResult 应该输出成功结果', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolResult('bash', 'hello world', 42)
    const output = consoleOutput.join('\n')
    expect(output).toContain('bash')
    expect(output).toContain('✓')
    expect(output).toContain('42ms')
  })

  it('showToolResult 应该输出错误结果', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.showToolResult('bash', 'command not found', 100, true)
    const output = consoleOutput.join('\n')
    expect(output).toContain('bash')
    expect(output).toContain('✗')
    expect(output).toContain('100ms')
    expect(output).toContain('command not found')
  })

  it('showToolResult 应该截断超过 200 字符的错误结果', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    const longResult = 'x'.repeat(300)
    display.showToolResult('bash', longResult, 10, true)
    const output = consoleOutput.join('\n')
    // 错误结果应包含截断标记
    expect(output).toContain('...')
  })

  it('startThinking 应该启动 spinner 并写入 stdout', async () => {
    const localOutput: string[] = []
    const originalWrite = process.stdout.write
    process.stdout.write = ((chunk: string | Uint8Array) => {
      localOutput.push(typeof chunk === 'string' ? chunk : new TextDecoder().decode(chunk))
      return true
    }) as any
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.startThinking()
    await new Promise((r) => setTimeout(r, 150))
    // 应该有 spinner 帧输出
    expect(localOutput.length).toBeGreaterThan(0)
    display.stopThinking()
    process.stdout.write = originalWrite
  })

  it('stopThinking 应该可以安全调用而不报错', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    // 没有启动 spinner 时调用 stopThinking 不应报错
    expect(() => display.stopThinking()).not.toThrow()
    // 启动后停止也不应报错
    display.startThinking()
    await new Promise((r) => setTimeout(r, 50))
    expect(() => display.stopThinking()).not.toThrow()
  })

  it('cleanup 应该可以安全调用而不报错', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    expect(() => display.cleanup()).not.toThrow()
    display.startThinking()
    await new Promise((r) => setTimeout(r, 50))
    expect(() => display.cleanup()).not.toThrow()
  })

  it('showToolResult 应该先停止 thinking 再输出然后重新启动 thinking', async () => {
    const localOutput: string[] = []
    const originalWrite = process.stdout.write
    process.stdout.write = ((chunk: string | Uint8Array) => {
      localOutput.push(typeof chunk === 'string' ? chunk : new TextDecoder().decode(chunk))
      return true
    }) as any
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.startThinking()
    await new Promise((r) => setTimeout(r, 100))
    // showToolResult 应自动 stopThinking，输出结果，再 startThinking
    display.showToolResult('bash', 'done', 50)
    localOutput.length = 0
    await new Promise((r) => setTimeout(r, 200))
    // showToolResult 后会重新 startThinking，应该有 braille 帧
    const brailleChars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    const hasBraille = localOutput.some((s) =>
      brailleChars.some((b) => s.includes(b))
    )
    expect(hasBraille).toBe(true)
    display.stopThinking()
    process.stdout.write = originalWrite
  })

  it('重复调用 stopThinking 不应报错', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    expect(() => display.stopThinking()).not.toThrow()
    display.startThinking()
    display.stopThinking()
    expect(() => display.stopThinking()).not.toThrow()
  })

  it('重复调用 startThinking 不应创建多个 spinner', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()
    display.startThinking()
    // 第二次调用不应抛出异常
    expect(() => display.startThinking()).not.toThrow()
    display.stopThinking()
  })

  // ===== CQR HIGH FIX TESTS =====

  it('HIGH-1: showToolStart 应在打印前停止活跃的 thinking spinner', async () => {
    let stopCalled = false
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()

    // 模拟活跃的 spinner：直接设置 activeSpinner 并 mock stopThinking
    const originalStopThinking = display.stopThinking.bind(display)
    display.stopThinking = () => {
      stopCalled = true
      originalStopThinking()
    }
    display.startThinking()
    await new Promise((r) => setTimeout(r, 50))

    // 调用 showToolStart —— 应先 stopThinking
    display.showToolStart('bash', { command: 'echo hi' })
    expect(stopCalled).toBe(true)
    display.stopThinking()
  })

  it('HIGH-2: formatDetail 应安全处理非字符串的 content（如 number）', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()

    // content 为 number 时不应抛出 TypeError
    expect(() => {
      display.showToolStart('file_write', { path: '/tmp/test.txt', content: 12345 })
    }).not.toThrow()

    // content 为 object 时不应抛出 TypeError
    expect(() => {
      display.showToolStart('file_write', { path: '/tmp/test.txt', content: { nested: true } })
    }).not.toThrow()

    // content 为 null 时不应抛出 TypeError
    expect(() => {
      display.showToolStart('file_write', { path: '/tmp/test.txt', content: null })
    }).not.toThrow()
  })

  it('HIGH-3: showToolResult 应安全处理 null/undefined result', async () => {
    const { ToolDisplay } = await import('../src/cli/tool-display.js')
    const display = new ToolDisplay()

    // null result 不应抛出 TypeError
    expect(() => {
      display.showToolResult('bash', null as any, 100)
    }).not.toThrow()

    // undefined result 不应抛出 TypeError
    expect(() => {
      display.showToolResult('bash', undefined as any, 100)
    }).not.toThrow()

    display.stopThinking()
  })
})

describe('Display', () => {
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

  it('应该从 src/cli/display.ts 导出 formatResponse 函数', async () => {
    const { formatResponse } = await import('../src/cli/display.js')
    expect(formatResponse).toBeDefined()
    expect(typeof formatResponse).toBe('function')
  })

  it('应该从 src/cli/display.ts 导出 renderHistory 函数', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    expect(renderHistory).toBeDefined()
    expect(typeof renderHistory).toBe('function')
  })

  it('formatResponse 应该原样返回传入的字符串', async () => {
    const { formatResponse } = await import('../src/cli/display.js')
    expect(formatResponse('hello')).toBe('hello')
    expect(formatResponse('')).toBe('')
  })

  it('renderHistory 应该渲染 user 消息', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    renderHistory([{ role: 'user', content: '你好' }])
    const output = consoleOutput.join('\n')
    expect(output).toContain('你好')
  })

  it('renderHistory 应该渲染 assistant 消息', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    renderHistory([{ role: 'assistant', content: '有什么可以帮你？' }])
    const output = consoleOutput.join('\n')
    expect(output).toContain('有什么可以帮你？')
  })

  it('renderHistory 应该渲染 system 消息', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    renderHistory([{ role: 'system', content: 'system prompt' }])
    const output = consoleOutput.join('\n')
    expect(output).toContain('system prompt')
  })

  it('renderHistory 应该处理多条消息', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    renderHistory([
      { role: 'user', content: 'msg1' },
      { role: 'assistant', content: 'msg2' },
    ])
    const output = consoleOutput.join('\n')
    expect(output).toContain('msg1')
    expect(output).toContain('msg2')
  })

  it('renderHistory 空数组不应报错', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    expect(() => renderHistory([])).not.toThrow()
  })

  it('renderHistory 应跳过 tool 角色消息且不产生任何输出', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    consoleOutput.length = 0
    renderHistory([{ role: 'tool', content: 'tool result data' }])
    // tool 消息不应产生任何 console.log 输出（包括空行）
    expect(consoleOutput.length).toBe(0)
  })

  it('renderHistory 混合消息中 tool 消息不应产生额外空行', async () => {
    const { renderHistory } = await import('../src/cli/display.js')
    consoleOutput.length = 0
    renderHistory([
      { role: 'user', content: '问题' },
      { role: 'tool', content: 'tool output' },
      { role: 'assistant', content: '回答' },
    ])
    // 应只有 user 和 assistant 的输出，不应有 tool 产生的空行
    const output = consoleOutput.join('\n')
    expect(output).toContain('问题')
    expect(output).toContain('回答')
    // 不应有纯空行出现在不该出现的位置
    // user 和 assistant 各自后面有一个空行，总共 4 次 console.log 调用
    expect(consoleOutput.length).toBe(4)
  })
})

describe('Completer', () => {
  it('应该从 src/cli/completer.ts 导出 createCompleter 函数', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    expect(createCompleter).toBeDefined()
    expect(typeof createCompleter).toBe('function')
  })

  it('createCompleter 应该返回一个函数', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    expect(typeof completer).toBe('function')
  })

  it('非斜杠输入应返回空匹配', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('hello')
    expect(hits).toEqual([])
    expect(line).toBe('hello')
  })

  it('空字符串应返回空匹配', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('')
    expect(hits).toEqual([])
    expect(line).toBe('')
  })

  it('/h 应匹配 /help', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('/h')
    expect(hits).toContain('/help')
    expect(line).toBe('/h')
  })

  it('/help 应匹配 /help', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('/help')
    expect(hits).toContain('/help')
    expect(line).toBe('/help')
  })

  it('/r 应匹配 /resume', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('/r')
    expect(hits).toContain('/resume')
    expect(line).toBe('/r')
  })

  it('/q 应匹配 /quit', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('/q')
    expect(hits).toContain('/quit')
    expect(line).toBe('/q')
  })

  it('/xyz 不匹配时应返回所有命令', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('/xyz')
    // 不匹配任何命令，应回退到所有命令
    expect(hits.length).toBeGreaterThan(0)
    expect(line).toBe('/xyz')
  })

  it('包含空格的输入应返回空匹配', async () => {
    const { createCompleter } = await import('../src/cli/completer.js')
    const completer = createCompleter()
    const [hits, line] = completer('/help me')
    expect(hits).toEqual([])
    expect(line).toBe('/help me')
  })
})

describe('PaginatedSelector', () => {
  let consoleOutput: string[]
  let consoleSpy: ReturnType<typeof mock>
  let originalStdin: typeof process.stdin
  let mockStdin: ReturnType<typeof mock>

  beforeEach(() => {
    consoleOutput = []
    consoleSpy = mock((...args: string[]) => {
      consoleOutput.push(args.join(' '))
    })
    console.log = consoleSpy
    console.clear = mock(() => {})
  })

  afterEach(() => {
    console.log = console.log
    console.clear = console.clear
  })

  it('应该从 src/cli/paginated-selector.ts 导出 paginatedSelect 函数', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')
    expect(paginatedSelect).toBeDefined()
    expect(typeof paginatedSelect).toBe('function')
  })

  it('空数组应立即返回 null', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')
    const result = await paginatedSelect([], (item: string) => item)
    expect(result).toBeNull()
  })

  it('单个元素按 Enter 应返回该元素', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    // 模拟 stdin 事件
    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    // 延迟发送 Enter 按键
    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\r'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['Apple']
    const result = await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    expect(result).toBe('Apple')
  })

  it('Esc 键应返回 null', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\x1b'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['A', 'B', 'C']
    const result = await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    expect(result).toBeNull()
  })

  it('q 键应返回 null', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('q'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['A', 'B']
    const result = await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    expect(result).toBeNull()
  })

  it('Ctrl+C 应返回 null', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\x03'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['X']
    const result = await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    expect(result).toBeNull()
  })

  it('按向下再 Enter 应选择第二项', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) {
        // 按下键移动到第二项
        handler(Buffer.from('\x1b[B'))
        // 按 Enter 确认
        handler(Buffer.from('\r'))
      }
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['First', 'Second', 'Third']
    const result = await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    expect(result).toBe('Second')
  })

  it('formatItem 应被调用来格式化显示', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\r'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = [42]
    const result = await paginatedSelect(items, (item, idx) => `Item #${idx}: ${item}`)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    const output = consoleOutput.join('\n')
    expect(output).toContain('Item #0: 42')
    expect(result).toBe(42)
  })

  it('多页时按右箭头应翻到下一页', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) {
        // 按右箭头翻到第二页
        handler(Buffer.from('\x1b[C'))
        // 按 Enter 选择第二页第一项（全局第 11 项）
        handler(Buffer.from('\r'))
      }
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    // 生成 15 项，默认 pageSize=10，第二页有 5 项
    const items = Array.from({ length: 15 }, (_, i) => `Item-${i + 1}`)
    const result = await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    expect(result).toBe('Item-11')
  })

  it('自定义 title 应显示在输出中', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\r'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['A']
    await paginatedSelect(items, (item) => item, 10, '选择会话')

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    const output = consoleOutput.join('\n')
    expect(output).toContain('选择会话')
  })

  it('pageSize 参数应控制每页显示数量', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\x1b')) // Esc 取消
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = Array.from({ length: 5 }, (_, i) => `Item-${i}`)
    await paginatedSelect(items, (item) => item, 3, 'Test')

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    const output = consoleOutput.join('\n')
    // pageSize=3，5 项应分为 2 页
    expect(output).toContain('1/2')
    expect(output).toContain('5 项')
  })

  it('应显示页码信息', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\x1b'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['A', 'B', 'C']
    await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    const output = consoleOutput.join('\n')
    expect(output).toContain('第 1/1 页')
    expect(output).toContain('共 3 项')
  })

  it('应显示操作提示', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\x1b'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['A']
    await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    const output = consoleOutput.join('\n')
    expect(output).toContain('Enter')
    expect(output).toContain('Esc')
  })

  it('选中项应有高亮标记', async () => {
    const { paginatedSelect } = await import('../src/cli/paginated-selector.js')

    const listeners: ((chunk: Buffer) => void)[] = []
    const origOn = process.stdin.on.bind(process.stdin)
    const origRemove = process.stdin.removeListener.bind(process.stdin)

    setTimeout(() => {
      const handler = listeners[listeners.length - 1]
      if (handler) handler(Buffer.from('\x1b'))
    }, 50)

    process.stdin.on = ((event: string, fn: any) => {
      if (event === 'data') listeners.push(fn)
      return process.stdin
    }) as any
    process.stdin.removeListener = (() => {}) as any

    const items = ['Apple', 'Banana']
    await paginatedSelect(items, (item) => item)

    process.stdin.on = origOn
    process.stdin.removeListener = origRemove

    const output = consoleOutput.join('\n')
    // 第一项应有 > 高亮标记
    expect(output).toContain('> 1.')
  })
})
