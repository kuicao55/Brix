import { describe, expect, it } from 'bun:test'

describe('THEME', () => {
  it('应该从 src/cli/theme.ts 导出 THEME', async () => {
    const { THEME } = await import('../src/cli/theme.js')
    expect(THEME).toBeDefined()
    expect(typeof THEME).toBe('object')
  })

  it('应该包含 markdown 样式组', async () => {
    const { THEME } = await import('../src/cli/theme.js')
    expect(THEME.markdown).toBeDefined()
    expect(typeof THEME.markdown.h1).toBe('function')
    expect(typeof THEME.markdown.h2).toBe('function')
    expect(typeof THEME.markdown.h3).toBe('function')
    expect(typeof THEME.markdown.code).toBe('function')
    expect(typeof THEME.markdown.codeBlock).toBe('function')
    expect(typeof THEME.markdown.link).toBe('function')
    expect(typeof THEME.markdown.em).toBe('function')
    expect(typeof THEME.markdown.strong).toBe('function')
    expect(typeof THEME.markdown.blockquote).toBe('function')
  })

  it('应该包含 tool 样式组', async () => {
    const { THEME } = await import('../src/cli/theme.js')
    expect(THEME.tool).toBeDefined()
    expect(typeof THEME.tool.border).toBe('function')
    expect(typeof THEME.tool.name).toBe('function')
    expect(typeof THEME.tool.success).toBe('function')
    expect(typeof THEME.tool.error).toBe('function')
  })

  it('应该包含 spinner 样式组', async () => {
    const { THEME } = await import('../src/cli/theme.js')
    expect(THEME.spinner).toBeDefined()
    expect(typeof THEME.spinner.active).toBe('function')
    expect(typeof THEME.spinner.done).toBe('function')
    expect(typeof THEME.spinner.failed).toBe('function')
  })

  it('应该包含 stage 样式组', async () => {
    const { THEME } = await import('../src/cli/theme.js')
    expect(THEME.stage).toBeDefined()
    expect(typeof THEME.stage.name).toBe('function')
    expect(typeof THEME.stage.time).toBe('function')
    expect(typeof THEME.stage.detail).toBe('function')
  })

  it('样式函数应该可调用并返回字符串', async () => {
    const { THEME } = await import('../src/cli/theme.js')
    // chalk 函数调用后应返回字符串（非 TTY 环境可能不含 ANSI 码）
    const result = THEME.markdown.h1('test')
    expect(typeof result).toBe('string')
    expect(result).toContain('test')
  })

  it('THEME 应该是只读的 (as const)', async () => {
    const { THEME } = await import('../src/cli/theme.js')
    // TypeScript as const 断言在运行时不影响可写性，
    // 但我们可以验证结构的完整性
    expect(Object.keys(THEME)).toEqual(['markdown', 'tool', 'spinner', 'stage'])
  })
})
