import * as fs from 'node:fs'
import * as path from 'node:path'
import { BaseTool } from '../base.js'

/**
 * 文件编辑工具 — 通过文本替换安全编辑文件
 *
 * 安全约束:
 * - 路径必须在 dataDir 目录内（防止路径遍历，使用 realpath 防止 symlink 绕过）
 * - 拒绝符号链接（防止 symlink 攻击）
 * - old_text 必须在文件中存在且唯一（恰好出现 1 次）
 * - 原子写入：写入临时文件，fsync，rename
 */
export class FileEditTool extends BaseTool {
  readonly name = 'file_edit'
  readonly description = 'Edit file by replacing text'
  readonly inputSchema = {
    type: 'object',
    properties: {
      path: { type: 'string', description: '要编辑的文件路径' },
      old_text: { type: 'string', description: '要替换的文本' },
      new_text: { type: 'string', description: '替换后的文本' },
    },
    required: ['path', 'old_text', 'new_text'],
  }

  private readonly allowedRoot: string
  private readonly realAllowedRoot: string

  constructor(dataDir: string = process.cwd()) {
    super()
    this.allowedRoot = path.resolve(dataDir)
    try {
      this.realAllowedRoot = fs.realpathSync(this.allowedRoot)
    } catch {
      this.realAllowedRoot = this.allowedRoot
    }
  }

  /**
   * 安全解析路径的真实位置，处理 macOS /var -> /private/var 等情况
   * 如果文件本身不存在，尝试解析其父目录
   */
  private safeRealPath(filePath: string): string {
    try {
      return fs.realpathSync(filePath)
    } catch {
      const dir = path.dirname(filePath)
      const base = path.basename(filePath)
      try {
        return path.join(fs.realpathSync(dir), base)
      } catch {
        return path.resolve(filePath)
      }
    }
  }

  /**
   * 验证路径安全性：containment 检查 + 符号链接拒绝
   */
  private validatePath(filePath: string): void {
    const resolved = path.resolve(filePath)
    const realResolved = this.safeRealPath(resolved)

    // 路径必须在 allowedRoot 内（使用真实路径比较）
    if (
      !realResolved.startsWith(this.realAllowedRoot + path.sep) &&
      realResolved !== this.realAllowedRoot
    ) {
      throw new Error(
        `Path "${filePath}" is outside the allowed root directory`
      )
    }

    // 检查路径是否为符号链接
    let stat: fs.Stats
    try {
      stat = fs.lstatSync(resolved)
    } catch {
      throw new Error(`File not found: "${filePath}"`)
    }

    if (stat.isSymbolicLink()) {
      throw new Error(
        `Path "${filePath}" is a symbolic link, which is not allowed`
      )
    }

    if (!stat.isFile()) {
      throw new Error(`Path "${filePath}" is not a file`)
    }
  }

  /**
   * 统计 old_text 在 content 中出现的次数
   */
  private countOccurrences(content: string, searchText: string): number {
    if (searchText === '') return 0
    let count = 0
    let pos = 0
    while (true) {
      const idx = content.indexOf(searchText, pos)
      if (idx === -1) break
      count++
      pos = idx + searchText.length
    }
    return count
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    const filePath = params.path
    const oldText = params.old_text
    const newText = params.new_text

    // 参数校验
    if (typeof filePath !== 'string' || !filePath) {
      throw new Error('path 参数必须是非空字符串')
    }
    if (typeof oldText !== 'string') {
      throw new Error('old_text 参数必须是字符串')
    }
    if (typeof newText !== 'string') {
      throw new Error('new_text 参数必须是字符串')
    }

    // 安全路径验证（包含文件存在性检查）
    this.validatePath(filePath)

    const resolved = path.resolve(filePath)

    // 读取文件内容
    const content = fs.readFileSync(resolved, 'utf-8')

    // 检查 old_text 是否存在
    const occurrences = this.countOccurrences(content, oldText)
    if (occurrences === 0) {
      throw new Error(
        `old_text 在文件中不存在: "${oldText}"`
      )
    }

    // 检查 old_text 是否唯一
    if (occurrences > 1) {
      throw new Error(
        `old_text 在文件中出现 ${occurrences} 次，不唯一，必须恰好出现 1 次才能安全替换`
      )
    }

    // 执行替换
    const newContent = content.replace(oldText, newText)

    // 原子写入：临时文件 -> fsync -> rename
    const tmpFile = resolved + `.tmp.${process.pid}.${Date.now()}`
    try {
      const fd = fs.openSync(tmpFile, 'w')
      try {
        fs.writeSync(fd, newContent, 0, 'utf-8')
        fs.fsyncSync(fd)
      } finally {
        fs.closeSync(fd)
      }
      fs.renameSync(tmpFile, resolved)
    } catch (err) {
      // 清理临时文件
      try {
        fs.unlinkSync(tmpFile)
      } catch {
        // 忽略清理失败
      }
      throw err
    }

    return `成功编辑文件: ${filePath}`
  }
}
