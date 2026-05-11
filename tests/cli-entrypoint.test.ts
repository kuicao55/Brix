import { describe, expect, it } from 'bun:test'
import { existsSync } from 'fs'

describe('CLI 入口', () => {
  it('入口文件应该存在', () => {
    // cli.ts 在模块级别直接调用 main()，不导出
    expect(existsSync('src/entrypoints/cli.ts')).toBe(true)
  })

  it('BrixCLI 应该存在', () => {
    expect(existsSync('src/cli/app.ts')).toBe(true)
  })
})
