import { describe, expect, it } from 'bun:test'

describe('CLI 入口', () => {
  it('应该导出 main 函数', async () => {
    const cli = await import('../src/entrypoints/cli.js')
    expect(cli.main).toBeDefined()
    expect(typeof cli.main).toBe('function')
  })
})
