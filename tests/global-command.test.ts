/**
 * 全局命令配置测试 — 验证 build 和 bun link 配置正确
 *
 * TDD 约定：
 *   - 验证 package.json 的 bin 字段指向 dist/cli.js
 *   - 验证 build 脚本存在
 *   - 验证构建后 dist/cli.js 存在且可执行
 *   - 验证全局命令 brix 已注册
 */
import { describe, expect, it } from 'bun:test'
import { readFile, access } from 'fs/promises'
import { join } from 'path'

const ROOT = join(import.meta.dir, '..')

describe('全局命令配置', () => {
  it('package.json 应该有 bin 字段指向 dist/cli.js', async () => {
    const pkg = JSON.parse(await readFile(join(ROOT, 'package.json'), 'utf-8'))
    expect(pkg.bin).toBeDefined()
    expect(pkg.bin.brix).toBe('dist/cli.js')
  })

  it('package.json 应该有 build 脚本', async () => {
    const pkg = JSON.parse(await readFile(join(ROOT, 'package.json'), 'utf-8'))
    expect(pkg.scripts).toBeDefined()
    expect(pkg.scripts.build).toBeDefined()
    expect(pkg.scripts.build).toContain('dist/cli.js')
  })

  it('构建后 dist/cli.js 应该存在', async () => {
    // 先执行构建
    const result = Bun.spawnSync(['bun', 'run', 'build'], {
      cwd: ROOT,
      stdout: 'pipe',
      stderr: 'pipe',
    })
    expect(result.exitCode).toBe(0)

    // 验证 dist/cli.js 存在（access 成功即表示文件存在）
    const cliPath = join(ROOT, 'dist', 'cli.js')
    let accessError: unknown = null
    try {
      await access(cliPath)
    } catch (e) {
      accessError = e
    }
    expect(accessError).toBeNull()
  })

  it('dist/cli.js 应该包含 shebang 行', async () => {
    const cliContent = await readFile(join(ROOT, 'dist', 'cli.js'), 'utf-8')
    expect(cliContent.startsWith('#!/usr/bin/env bun')).toBe(true)
  })

  it('bun link 后应该能注册 brix 全局命令', async () => {
    // 执行 bun link
    const linkResult = Bun.spawnSync(['bun', 'link'], {
      cwd: ROOT,
      stdout: 'pipe',
      stderr: 'pipe',
    })
    expect(linkResult.exitCode).toBe(0)

    // 验证 brix 命令已注册
    const whichResult = Bun.spawnSync(['which', 'brix'], {
      stdout: 'pipe',
      stderr: 'pipe',
    })
    expect(whichResult.exitCode).toBe(0)
    const brixPath = whichResult.stdout.toString().trim()
    expect(brixPath).toContain('brix')
  })
})
