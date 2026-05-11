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
