/**
 * CLI 入口集成验证测试 — Phase 3
 * 验证所有 Phase 3 模块（Router, Orchestrator, Capability）可正确导入和运行
 */
import { describe, it, expect } from 'vitest'
import { main } from './cli.js'

describe('CLI 集成验证', () => {
  it('main() should run Phase 3 verification without errors', async () => {
    // main() 不应抛出异常
    await expect(main()).resolves.toBeUndefined()
  })

  it('main() should produce Phase 3 verification output', async () => {
    const logs: string[] = []
    const originalLog = console.log
    console.log = (...args: unknown[]) => {
      logs.push(args.map(String).join(' '))
    }
    try {
      await main()
    } finally {
      console.log = originalLog
    }

    const output = logs.join('\n')

    // 验证关键输出
    expect(output).toContain('Phase 3 Complete')
    expect(output).toContain('Intent:')
    expect(output).toContain('Complexity:')
    expect(output).toContain('Model:')
    expect(output).toContain('Orchestrator created')
    expect(output).toContain('ToolRunner registered')
    expect(output).toContain('Phase 3 verification complete!')
  })
})
