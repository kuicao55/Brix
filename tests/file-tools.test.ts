import { describe, expect, it, beforeEach, afterEach } from 'bun:test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import * as os from 'node:os'
import { FileReadTool } from '../src/capability/tools/file-read.js'

/**
 * FileReadTool 测试
 * 使用临时目录作为沙箱，测试安全读取、路径校验、符号链接拒绝、大文件截断
 */

describe('FileReadTool', () => {
  let tmpDir: string
  let tool: FileReadTool

  beforeEach(() => {
    // 创建临时目录作为沙箱根目录
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'file-read-test-'))
    tool = new FileReadTool(tmpDir)
  })

  afterEach(() => {
    // 清理临时目录
    fs.rmSync(tmpDir, { recursive: true, force: true })
  })

  // --- 基本属性 ---

  it('应有正确的 name 和 description', () => {
    expect(tool.name).toBe('file_read')
    expect(tool.description).toBe('Read file contents')
  })

  it('inputSchema 应定义 path 参数为 required', () => {
    expect(tool.inputSchema).toEqual({
      type: 'object',
      properties: {
        path: { type: 'string', description: '要读取的文件路径' },
      },
      required: ['path'],
    })
  })

  it('应返回正确的 OpenAI schema', () => {
    const schema = tool.toOpenAiSchema()
    expect(schema).toEqual({
      type: 'function',
      function: {
        name: 'file_read',
        description: 'Read file contents',
        parameters: {
          type: 'object',
          properties: {
            path: { type: 'string', description: '要读取的文件路径' },
          },
          required: ['path'],
        },
      },
    })
  })

  // --- 正常读取 ---

  it('应正确读取文本文件内容', async () => {
    const filePath = path.join(tmpDir, 'hello.txt')
    fs.writeFileSync(filePath, '你好世界')

    const result = await tool.execute({ path: filePath })
    expect(result).toBe('你好世界')
  })

  it('应正确读取空文件', async () => {
    const filePath = path.join(tmpDir, 'empty.txt')
    fs.writeFileSync(filePath, '')

    const result = await tool.execute({ path: filePath })
    expect(result).toBe('')
  })

  it('应正确读取多行文件', async () => {
    const filePath = path.join(tmpDir, 'multiline.txt')
    const content = '第一行\n第二行\n第三行'
    fs.writeFileSync(filePath, content)

    const result = await tool.execute({ path: filePath })
    expect(result).toBe(content)
  })

  // --- 安全检查：路径越界 ---

  it('应拒绝 allowedRoot 之外的路径', async () => {
    const outsidePath = path.join(os.tmpdir(), 'outside.txt')
    fs.writeFileSync(outsidePath, 'secret')

    await expect(tool.execute({ path: outsidePath })).rejects.toThrow(
      /outside.*allowed/i
    )

    // 清理
    fs.unlinkSync(outsidePath)
  })

  it('应拒绝使用 .. 遍历到 allowedRoot 之外的路径', async () => {
    const escapePath = path.join(tmpDir, '..', '..', 'etc', 'passwd')

    await expect(tool.execute({ path: escapePath })).rejects.toThrow(
      /outside.*allowed/i
    )
  })

  // --- 安全检查：符号链接 ---

  it('应拒绝符号链接文件', async () => {
    const realFile = path.join(tmpDir, 'real.txt')
    const symlinkFile = path.join(tmpDir, 'link.txt')
    fs.writeFileSync(realFile, '真实内容')
    fs.symlinkSync(realFile, symlinkFile)

    await expect(tool.execute({ path: symlinkFile })).rejects.toThrow(
      /symbolic|symlink/i
    )
  })

  // --- 文件不存在 ---

  it('文件不存在时应抛出清晰错误', async () => {
    const missingPath = path.join(tmpDir, 'nonexistent.txt')

    await expect(tool.execute({ path: missingPath })).rejects.toThrow(
      /not found|不存在/i
    )
  })

  // --- 参数校验 ---

  it('缺少 path 参数应抛出错误', async () => {
    await expect(tool.execute({})).rejects.toThrow()
  })

  it('path 参数为非字符串应抛出错误', async () => {
    await expect(tool.execute({ path: 123 })).rejects.toThrow()
  })

  // --- 大文件截断 ---

  it('超过 100KB 的文件应截断并附加截断提示', async () => {
    const filePath = path.join(tmpDir, 'large.txt')
    // 创建一个刚好超过 100KB 的文件
    const largeContent = 'A'.repeat(100 * 1024 + 100)
    fs.writeFileSync(filePath, largeContent)

    const result = await tool.execute({ path: filePath })
    expect(result.length).toBeLessThanOrEqual(100 * 1024 + '... (truncated at 100KB)'.length)
    expect(result).toEndWith('... (truncated at 100KB)')
  })

  it('不超过 100KB 的文件不应截断', async () => {
    const filePath = path.join(tmpDir, 'small.txt')
    const content = 'A'.repeat(100)
    fs.writeFileSync(filePath, content)

    const result = await tool.execute({ path: filePath })
    expect(result).toBe(content)
    expect(result).not.toContain('truncated')
  })

  it('恰好 100KB 的文件不应截断', async () => {
    const filePath = path.join(tmpDir, 'exact.txt')
    const content = 'A'.repeat(100 * 1024)
    fs.writeFileSync(filePath, content)

    const result = await tool.execute({ path: filePath })
    expect(result).toBe(content)
    expect(result).not.toContain('truncated')
  })

  // --- 通过 ToolRunner 集成 ---

  it('应能通过 ToolRunner 注册和执行', async () => {
    const { ToolRunner } = await import('../src/capability/runner.js')
    const runner = new ToolRunner()
    runner.register(tool)

    const filePath = path.join(tmpDir, 'runner-test.txt')
    fs.writeFileSync(filePath, 'runner works')

    const result = await runner.run('file_read', { path: filePath })
    expect(result).toBe('runner works')
  })
})
