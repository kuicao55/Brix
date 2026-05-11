import * as fs from 'node:fs'
import * as path from 'node:path'
import * as os from 'node:os'
import { BaseTool } from '../base.js'

/**
 * 文件写入工具 — 安全写入文件内容
 *
 * 安全约束:
 * - 路径必须在 dataDir 目录内（防止路径遍历，使用 realpath 防止 symlink 绕过）
 * - 拒绝符号链接（防止 symlink 攻击）
 * - 原子写入：写入临时文件，fsync，rename
 * - 自动创建不存在的父目录
 */
export class FileWriteTool extends BaseTool {
  readonly name = 'file_write'
  readonly description = 'Write content to a file'
  readonly inputSchema = {
    type: 'object',
    properties: {
      path: { type: 'string', description: '要写入的文件路径' },
      content: { type: 'string', description: '要写入的内容' },
    },
    required: ['path', 'content'],
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
   * 向上遍历找到最近存在的祖先目录，用 realpath 解析后再拼接剩余路径
   * 这样即使父目录尚不存在，也能正确解析路径中的符号链接
   */
  private safeRealPath(filePath: string): string {
    const resolved = path.resolve(filePath)

    // 尝试直接解析（文件已存在的情况）
    try {
      return fs.realpathSync(resolved)
    } catch {
      // 向上遍历找到最近存在的祖先
      let current = resolved
      const segments: string[] = []

      while (current !== path.dirname(current)) {
        try {
          const real = fs.realpathSync(current)
          return path.join(real, ...segments.reverse())
        } catch {
          segments.push(path.basename(current))
          current = path.dirname(current)
        }
      }

      // 所有祖先都不存在，回退到 resolve
      return resolved
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

    // 检查路径是否为符号链接（仅当文件已存在时）
    try {
      const stat = fs.lstatSync(resolved)
      if (stat.isSymbolicLink()) {
        throw new Error(
          `Path "${filePath}" is a symbolic link, which is not allowed`
        )
      }
    } catch (e) {
      // 文件不存在是正常的（写入新文件），重新抛出其他错误
      if (e instanceof Error && e.message.includes('symbolic link')) {
        throw e
      }
    }
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    const filePath = params.path
    const content = params.content

    // 参数校验
    if (typeof filePath !== 'string' || !filePath) {
      throw new Error('path 参数必须是非空字符串')
    }
    if (typeof content !== 'string') {
      throw new Error('content 参数必须是字符串')
    }

    // 安全路径验证
    this.validatePath(filePath)

    const resolved = path.resolve(filePath)

    // 确保父目录存在
    const parentDir = path.dirname(resolved)
    fs.mkdirSync(parentDir, { recursive: true })

    // 原子写入：临时文件 -> fsync -> rename
    const tmpFile = resolved + `.tmp.${process.pid}.${Date.now()}`
    try {
      const fd = fs.openSync(tmpFile, 'w')
      try {
        fs.writeSync(fd, content, 0, 'utf-8')
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

    return `成功写入文件: ${filePath}`
  }
}
