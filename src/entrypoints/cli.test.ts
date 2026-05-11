/**
 * CLI 入口测试 — 验证入口文件正确使用 BrixCLI
 *
 * TDD 约定：
 *   - mock BrixCLI 防止真实 REPL 启动
 *   - 验证入口直接调用 main()，不导出
 */
import { describe, expect, it, mock, beforeEach } from 'bun:test'

// 在模块级别 mock，确保 import 前生效
const runSpy = mock(() => Promise.resolve())

mock.module('../cli/app.js', () => ({
  BrixCLI: class MockBrixCLI {
    run = runSpy
  }
}))

describe('CLI 入口', () => {
  beforeEach(() => {
    runSpy.mockClear()
  })

  it('应该创建 BrixCLI 实例并调用 run() 启动 REPL', async () => {
    // 动态导入触发 main()
    await import('./cli.js')
    // 等待异步 main 执行完成
    await Bun.sleep(200)

    expect(runSpy).toHaveBeenCalled()
  })

  it('不应该导出 main 函数（入口点直接调用）', async () => {
    const mod = await import('./cli.js')
    expect(mod.main).toBeUndefined()
  })
})
