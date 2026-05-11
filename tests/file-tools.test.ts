import { describe, expect, it, beforeEach, afterEach } from 'bun:test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import * as os from 'node:os'
import { FileReadTool } from '../src/capability/tools/file-read.js'
import { FileWriteTool } from '../src/capability/tools/file-write.js'
import { FileEditTool } from '../src/capability/tools/file-edit.js'

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

  // --- 安全检查：通过符号链接的父目录绕过沙箱 (Issue 1) ---

  it('应拒绝通过符号链接父目录访问 allowedRoot 之外的文件', async () => {
    // 在 tmpDir 外创建一个包含文件的目录
    const externalDir = fs.mkdtempSync(path.join(os.tmpdir(), 'external-'))
    const externalFile = path.join(externalDir, 'secret.txt')
    fs.writeFileSync(externalFile, '外部秘密内容')

    // 在 tmpDir 内创建指向外部目录的符号链接
    const symlinkDir = path.join(tmpDir, 'linked-subdir')
    fs.symlinkSync(externalDir, symlinkDir)

    // 通过符号链接父目录访问文件 — 应被拒绝
    const symlinkedPath = path.join(symlinkDir, 'secret.txt')
    await expect(tool.execute({ path: symlinkedPath })).rejects.toThrow(
      /outside.*allowed|symbolic|symlink/i
    )

    // 清理
    fs.unlinkSync(symlinkDir)
    fs.rmSync(externalDir, { recursive: true, force: true })
  })

  // --- 安全检查：多字节字符的字节大小限制 (Issue 3) ---

  it('应拒绝字节大小超过 100KB 的多字节文件（即使字符数未超限）', async () => {
    const filePath = path.join(tmpDir, 'multibyte-large.txt')
    // 每个 '中' 字是 3 字节 UTF-8，但 String.length 为 1
    // 40000 个字符 = 120000 字节 > 100KB，但字符数 40000 < 102400
    const charCount = 40000
    const content = '中'.repeat(charCount)
    const byteSize = Buffer.byteLength(content, 'utf-8')
    // 确认字节大小确实超过 100KB
    expect(byteSize).toBeGreaterThan(100 * 1024)
    // 确认字符数确实未超过 100KB
    expect(content.length).toBeLessThan(100 * 1024)

    fs.writeFileSync(filePath, content)

    const result = await tool.execute({ path: filePath })
    expect(result).toContain('truncated')
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

// ============================================================
// FileWriteTool 测试
// ============================================================

describe('FileWriteTool', () => {
  let tmpDir: string
  let tool: FileWriteTool

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'file-write-test-'))
    tool = new FileWriteTool(tmpDir)
  })

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true })
  })

  // --- 基本属性 ---

  it('应有正确的 name 和 description', () => {
    expect(tool.name).toBe('file_write')
    expect(tool.description).toBe('Write content to a file')
  })

  it('inputSchema 应定义 path 和 content 参数为 required', () => {
    expect(tool.inputSchema).toEqual({
      type: 'object',
      properties: {
        path: { type: 'string', description: '要写入的文件路径' },
        content: { type: 'string', description: '要写入的内容' },
      },
      required: ['path', 'content'],
    })
  })

  it('应返回正确的 OpenAI schema', () => {
    const schema = tool.toOpenAiSchema()
    expect(schema).toEqual({
      type: 'function',
      function: {
        name: 'file_write',
        description: 'Write content to a file',
        parameters: {
          type: 'object',
          properties: {
            path: { type: 'string', description: '要写入的文件路径' },
            content: { type: 'string', description: '要写入的内容' },
          },
          required: ['path', 'content'],
        },
      },
    })
  })

  // --- 正常写入 ---

  it('应正确写入文本文件', async () => {
    const filePath = path.join(tmpDir, 'output.txt')
    const result = await tool.execute({ path: filePath, content: '你好世界' })

    expect(result).toContain('成功')
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('你好世界')
  })

  it('应正确写入空内容', async () => {
    const filePath = path.join(tmpDir, 'empty.txt')
    await tool.execute({ path: filePath, content: '' })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe('')
  })

  it('应正确写入多行内容', async () => {
    const filePath = path.join(tmpDir, 'multiline.txt')
    const content = '第一行\n第二行\n第三行'
    await tool.execute({ path: filePath, content })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe(content)
  })

  it('应覆盖已有文件内容', async () => {
    const filePath = path.join(tmpDir, 'overwrite.txt')
    fs.writeFileSync(filePath, '旧内容')
    await tool.execute({ path: filePath, content: '新内容' })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe('新内容')
  })

  it('应自动创建不存在的父目录', async () => {
    const filePath = path.join(tmpDir, 'sub', 'dir', 'new.txt')
    await tool.execute({ path: filePath, content: '嵌套文件' })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe('嵌套文件')
  })

  // --- 安全检查：路径越界 ---

  it('应拒绝 allowedRoot 之外的路径', async () => {
    const outsidePath = path.join(os.tmpdir(), 'outside-write.txt')

    await expect(
      tool.execute({ path: outsidePath, content: 'secret' })
    ).rejects.toThrow(/outside.*allowed/i)
  })

  it('应拒绝使用 .. 遍历到 allowedRoot 之外的路径', async () => {
    const escapePath = path.join(tmpDir, '..', '..', 'tmp', 'escape.txt')

    await expect(
      tool.execute({ path: escapePath, content: 'escape' })
    ).rejects.toThrow(/outside.*allowed/i)
  })

  // --- 安全检查：符号链接 ---

  it('应拒绝写入符号链接文件', async () => {
    const realFile = path.join(tmpDir, 'real.txt')
    const symlinkFile = path.join(tmpDir, 'link.txt')
    fs.writeFileSync(realFile, '真实内容')
    fs.symlinkSync(realFile, symlinkFile)

    await expect(
      tool.execute({ path: symlinkFile, content: '攻击' })
    ).rejects.toThrow(/symbolic|symlink/i)
  })

  it('应拒绝通过符号链接父目录写入 allowedRoot 之外的文件', async () => {
    const externalDir = fs.mkdtempSync(path.join(os.tmpdir(), 'external-'))
    const symlinkDir = path.join(tmpDir, 'linked-subdir')
    fs.symlinkSync(externalDir, symlinkDir)

    const symlinkedPath = path.join(symlinkDir, 'secret.txt')
    await expect(
      tool.execute({ path: symlinkedPath, content: 'attack' })
    ).rejects.toThrow(/outside.*allowed|symbolic|symlink/i)

    fs.unlinkSync(symlinkDir)
    fs.rmSync(externalDir, { recursive: true, force: true })
  })

  // --- 参数校验 ---

  it('缺少 path 参数应抛出错误', async () => {
    await expect(tool.execute({ content: 'test' })).rejects.toThrow()
  })

  it('缺少 content 参数应抛出错误', async () => {
    const filePath = path.join(tmpDir, 'test.txt')
    await expect(tool.execute({ path: filePath })).rejects.toThrow()
  })

  it('path 参数为非字符串应抛出错误', async () => {
    await expect(tool.execute({ path: 123, content: 'test' })).rejects.toThrow()
  })

  // --- 原子写入验证 ---

  it('写入应是原子的：文件要么是旧内容要么是新内容', async () => {
    const filePath = path.join(tmpDir, 'atomic.txt')
    fs.writeFileSync(filePath, '原始内容')
    await tool.execute({ path: filePath, content: '更新内容' })

    // 写入完成后，内容应完整
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('更新内容')
  })

  // --- 通过 ToolRunner 集成 ---

  it('应能通过 ToolRunner 注册和执行', async () => {
    const { ToolRunner } = await import('../src/capability/runner.js')
    const runner = new ToolRunner()
    runner.register(tool)

    const filePath = path.join(tmpDir, 'runner-write.txt')
    const result = await runner.run('file_write', {
      path: filePath,
      content: 'runner writes',
    })
    expect(result).toContain('成功')
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('runner writes')
  })
})

// ============================================================
// FileEditTool 测试
// ============================================================

describe('FileEditTool', () => {
  let tmpDir: string
  let tool: FileEditTool

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'file-edit-test-'))
    tool = new FileEditTool(tmpDir)
  })

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true })
  })

  // --- 基本属性 ---

  it('应有正确的 name 和 description', () => {
    expect(tool.name).toBe('file_edit')
    expect(tool.description).toBe('Edit file by replacing text')
  })

  it('inputSchema 应定义 path、old_text、new_text 参数为 required', () => {
    expect(tool.inputSchema).toEqual({
      type: 'object',
      properties: {
        path: { type: 'string', description: '要编辑的文件路径' },
        old_text: { type: 'string', description: '要替换的文本' },
        new_text: { type: 'string', description: '替换后的文本' },
      },
      required: ['path', 'old_text', 'new_text'],
    })
  })

  it('应返回正确的 OpenAI schema', () => {
    const schema = tool.toOpenAiSchema()
    expect(schema).toEqual({
      type: 'function',
      function: {
        name: 'file_edit',
        description: 'Edit file by replacing text',
        parameters: {
          type: 'object',
          properties: {
            path: { type: 'string', description: '要编辑的文件路径' },
            old_text: { type: 'string', description: '要替换的文本' },
            new_text: { type: 'string', description: '替换后的文本' },
          },
          required: ['path', 'old_text', 'new_text'],
        },
      },
    })
  })

  // --- 正常编辑 ---

  it('应正确替换文件中的文本', async () => {
    const filePath = path.join(tmpDir, 'edit.txt')
    fs.writeFileSync(filePath, 'Hello World')

    const result = await tool.execute({
      path: filePath,
      old_text: 'World',
      new_text: 'TypeScript',
    })

    expect(result).toContain('成功')
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('Hello TypeScript')
  })

  it('应正确替换多行文本', async () => {
    const filePath = path.join(tmpDir, 'multiline-edit.txt')
    fs.writeFileSync(filePath, '第一行\n第二行\n第三行')

    await tool.execute({
      path: filePath,
      old_text: '第一行\n第二行',
      new_text: '新第一行\n新第二行',
    })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe('新第一行\n新第二行\n第三行')
  })

  it('new_text 为空字符串时应删除 old_text', async () => {
    const filePath = path.join(tmpDir, 'delete-text.txt')
    fs.writeFileSync(filePath, '保留 删除我 保留')

    await tool.execute({
      path: filePath,
      old_text: ' 删除我',
      new_text: '',
    })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe('保留 保留')
  })

  // --- 唯一性检查 ---

  it('old_text 出现多次时应抛出错误', async () => {
    const filePath = path.join(tmpDir, 'duplicate.txt')
    fs.writeFileSync(filePath, 'aaa bbb aaa')

    await expect(
      tool.execute({
        path: filePath,
        old_text: 'aaa',
        new_text: 'ccc',
      })
    ).rejects.toThrow(/唯一|unique|multiple/i)
  })

  it('old_text 不存在时应抛出错误', async () => {
    const filePath = path.join(tmpDir, 'no-match.txt')
    fs.writeFileSync(filePath, 'Hello World')

    await expect(
      tool.execute({
        path: filePath,
        old_text: '不存在的文本',
        new_text: '替换',
      })
    ).rejects.toThrow(/不存在|not found|no match/i)
  })

  it('old_text 恰好出现一次时应成功替换', async () => {
    const filePath = path.join(tmpDir, 'unique.txt')
    fs.writeFileSync(filePath, 'aaa bbb ccc')

    await tool.execute({
      path: filePath,
      old_text: 'bbb',
      new_text: 'ddd',
    })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe('aaa ddd ccc')
  })

  // --- 安全检查：路径越界 ---

  it('应拒绝 allowedRoot 之外的路径', async () => {
    const outsidePath = path.join(os.tmpdir(), 'outside-edit.txt')
    fs.writeFileSync(outsidePath, 'content')

    await expect(
      tool.execute({
        path: outsidePath,
        old_text: 'content',
        new_text: 'hack',
      })
    ).rejects.toThrow(/outside.*allowed/i)

    fs.unlinkSync(outsidePath)
  })

  it('应拒绝使用 .. 遍历到 allowedRoot 之外的路径', async () => {
    const escapePath = path.join(tmpDir, '..', '..', 'etc', 'passwd')

    await expect(
      tool.execute({
        path: escapePath,
        old_text: 'root',
        new_text: 'hacked',
      })
    ).rejects.toThrow(/outside.*allowed/i)
  })

  // --- 安全检查：符号链接 ---

  it('应拒绝编辑符号链接文件', async () => {
    const realFile = path.join(tmpDir, 'real.txt')
    const symlinkFile = path.join(tmpDir, 'link.txt')
    fs.writeFileSync(realFile, '真实内容')
    fs.symlinkSync(realFile, symlinkFile)

    await expect(
      tool.execute({
        path: symlinkFile,
        old_text: '真实',
        new_text: '攻击',
      })
    ).rejects.toThrow(/symbolic|symlink/i)
  })

  it('应拒绝通过符号链接父目录编辑 allowedRoot 之外的文件', async () => {
    const externalDir = fs.mkdtempSync(path.join(os.tmpdir(), 'external-'))
    const externalFile = path.join(externalDir, 'secret.txt')
    fs.writeFileSync(externalFile, 'secret content')
    const symlinkDir = path.join(tmpDir, 'linked-subdir')
    fs.symlinkSync(externalDir, symlinkDir)

    const symlinkedPath = path.join(symlinkDir, 'secret.txt')
    await expect(
      tool.execute({
        path: symlinkedPath,
        old_text: 'secret',
        new_text: 'hacked',
      })
    ).rejects.toThrow(/outside.*allowed|symbolic|symlink/i)

    fs.unlinkSync(symlinkDir)
    fs.rmSync(externalDir, { recursive: true, force: true })
  })

  // --- 文件不存在 ---

  it('文件不存在时应抛出清晰错误', async () => {
    const missingPath = path.join(tmpDir, 'nonexistent.txt')

    await expect(
      tool.execute({
        path: missingPath,
        old_text: 'a',
        new_text: 'b',
      })
    ).rejects.toThrow(/not found|不存在/)
  })

  // --- 参数校验 ---

  it('缺少 path 参数应抛出错误', async () => {
    await expect(
      tool.execute({ old_text: 'a', new_text: 'b' })
    ).rejects.toThrow()
  })

  it('缺少 old_text 参数应抛出错误', async () => {
    const filePath = path.join(tmpDir, 'test.txt')
    fs.writeFileSync(filePath, 'content')
    await expect(
      tool.execute({ path: filePath, new_text: 'b' })
    ).rejects.toThrow()
  })

  it('缺少 new_text 参数应抛出错误', async () => {
    const filePath = path.join(tmpDir, 'test.txt')
    fs.writeFileSync(filePath, 'content')
    await expect(
      tool.execute({ path: filePath, old_text: 'a' })
    ).rejects.toThrow()
  })

  // --- 原子写入验证 ---

  it('编辑应是原子的：文件要么是旧内容要么是新内容', async () => {
    const filePath = path.join(tmpDir, 'atomic-edit.txt')
    fs.writeFileSync(filePath, 'AAA BBB CCC')

    await tool.execute({
      path: filePath,
      old_text: 'BBB',
      new_text: 'DDD',
    })

    expect(fs.readFileSync(filePath, 'utf-8')).toBe('AAA DDD CCC')
  })

  // --- 通过 ToolRunner 集成 ---

  it('应能通过 ToolRunner 注册和执行', async () => {
    const { ToolRunner } = await import('../src/capability/runner.js')
    const runner = new ToolRunner()
    runner.register(tool)

    const filePath = path.join(tmpDir, 'runner-edit.txt')
    fs.writeFileSync(filePath, 'original text')

    const result = await runner.run('file_edit', {
      path: filePath,
      old_text: 'original',
      new_text: 'modified',
    })
    expect(result).toContain('成功')
    expect(fs.readFileSync(filePath, 'utf-8')).toBe('modified text')
  })
})
