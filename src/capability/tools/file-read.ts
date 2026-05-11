import * as fs from 'node:fs'
import * as path from 'node:path'
import { BaseTool } from '../base.js'

/**
 * 文件读取工具 — 安全读取文件内容
 *
 * 安全约束:
 * - 路径必须在 allowedRoot 目录内（防止路径遍历）
 * - 拒绝符号链接（防止 symlink 攻击）
 * - 文件大小限制 100KB，超过则截断
 */
export class FileReadTool extends BaseTool {
  readonly name = 'file_read'
  readonly description = 'Read file contents'
  readonly inputSchema = {
    type: 'object',
    properties: {
      path: { type: 'string', description: '要读取的文件路径' },
    },
    required: ['path'],
  }

  private readonly allowedRoot: string

  constructor(allowedRoot: string = process.cwd()) {
    super()
    this.allowedRoot = path.resolve(allowedRoot)
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    const filePath = params.path
    if (typeof filePath !== 'string' || !filePath) {
      throw new Error('path 参数必须是非空字符串')
    }

    // 解析为绝对路径
    const resolved = path.resolve(filePath)

    // 安全检查：路径必须在 allowedRoot 内
    if (!resolved.startsWith(this.allowedRoot + path.sep) && resolved !== this.allowedRoot) {
      throw new Error(
        `Path "${filePath}" is outside the allowed root directory`
      )
    }

    // 安全检查：拒绝符号链接
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

    // 读取文件内容
    const content = fs.readFileSync(resolved, 'utf-8')

    // 大小限制：100KB
    const MAX_SIZE = 100 * 1024
    if (content.length > MAX_SIZE) {
      return content.slice(0, MAX_SIZE) + '... (truncated at 100KB)'
    }

    return content
  }
}
