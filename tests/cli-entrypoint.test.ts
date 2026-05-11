import { describe, expect, it, spyOn, mock } from 'bun:test'

// Mock dotenv/config — 避免实际加载 .env 文件
mock.module('dotenv/config', () => ({}))

// 注意：不 mock loadConfig，使用真实实现（无配置文件时返回默认值）
// 这样不会影响其他测试文件的模块解析

describe('CLI 入口', () => {
  it('应该导出 main 函数', async () => {
    const cli = await import('../src/entrypoints/cli.js')
    expect(cli.main).toBeDefined()
    expect(typeof cli.main).toBe('function')
  })

  it('main() 应该输出 Phase 1 Complete 并加载配置', async () => {
    const cli = await import('../src/entrypoints/cli.js')
    const logs: string[] = []
    const consoleSpy = spyOn(console, 'log').mockImplementation((...args: unknown[]) => {
      logs.push(args.map(String).join(' '))
    })

    await cli.main()

    expect(logs.some(l => l.includes('Brix TypeScript Migration - Phase 1 Complete'))).toBe(true)
    expect(logs.some(l => l.includes('Config loaded:'))).toBe(true)
    // loadConfig 返回默认配置，engine 为 'state_machine'
    expect(logs.some(l => l.includes('state_machine'))).toBe(true)

    consoleSpy.mockRestore()
  })

  it('main() 应该在 loadConfig 抛异常时优雅处理', async () => {
    // 使用 spyOn 替代 mock.module 来模拟 loadConfig 失败
    const loader = await import('../src/config/loader.js')
    const errorSpy = spyOn(loader, 'loadConfig').mockImplementation(() => {
      throw new Error('Config load failed')
    })

    const cli = await import('../src/entrypoints/cli.js')
    const errorLogs: string[] = []
    const consoleSpy = spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
      errorLogs.push(args.map(String).join(' '))
    })

    // 应该不抛异常 — fail gracefully
    await expect(cli.main()).resolves.toBeUndefined()
    expect(errorLogs.some(l => l.includes('Failed to load config'))).toBe(true)

    consoleSpy.mockRestore()
    errorSpy.mockRestore()
  })
})
