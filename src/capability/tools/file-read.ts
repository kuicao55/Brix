import * as fs from 'node:fs'
import * as path from 'node:path'
import { BaseTool } from '../base.js'

/**
 * 文件读取工具 — 安全读取文件内容
 *
 * 安全约束:
 * - 路径必须在 allowedRoot 目录内（防止路径遍历，使用 realpath 防止 symlink 绕过）
 * - 拒绝符号链接（防止 symlink 攻击，双次 lstat + inode 比对防止 TOCTOU）
 * - 文件大小限制 100KB 字节（非字符数），超过则截断
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
  private readonly realAllowedRoot: string

  constructor(allowedRoot: string = process.cwd()) {
    super()
    this.allowedRoot = path.resolve(allowedRoot)
    // Issue 1 修复：使用 realpath 解析 allowedRoot 中的符号链接
    try {
      this.realAllowedRoot = fs.realpathSync(this.allowedRoot)
    } catch {
      // 如果 allowedRoot 本身不存在，回退到 resolve 结果
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
      // 文件不存在时，尝试解析父目录的真实路径
      const dir = path.dirname(filePath)
      const base = path.basename(filePath)
      try {
        return path.join(fs.realpathSync(dir), base)
      } catch {
        // 父目录也不存在，回退到 resolve
        return path.resolve(filePath)
      }
    }
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    const filePath = params.path
    if (typeof filePath !== 'string' || !filePath) {
      throw new Error('path 参数必须是非空字符串')
    }

    // 解析为绝对路径
    const resolved = path.resolve(filePath)

    // Issue 1 修复：使用 realpath 解析路径中的符号链接，再做 containment 检查
    const realResolved = this.safeRealPath(resolved)

    // 安全检查：路径必须在 allowedRoot 内（使用真实路径比较）
    if (
      !realResolved.startsWith(this.realAllowedRoot + path.sep) &&
      realResolved !== this.realAllowedRoot
    ) {
      throw new Error(
        `Path "${filePath}" is outside the allowed root directory`
      )
    }

    // Issue 2 修复：双次 lstat + inode 比对，防止 TOCTOU 竞态
    // 第一次 lstat：检查路径是否为符号链接
    let firstStat: fs.Stats
    try {
      firstStat = fs.lstatSync(resolved)
    } catch {
      throw new Error(`File not found: "${filePath}"`)
    }

    if (firstStat.isSymbolicLink()) {
      throw new Error(
        `Path "${filePath}" is a symbolic link, which is not allowed`
      )
    }

    if (!firstStat.isFile()) {
      throw new Error(`Path "${filePath}" is not a file`)
    }

    // 打开文件获取 fd
    let fd: number
    try {
      fd = fs.openSync(resolved, 'r')
    } catch {
      throw new Error(`File not found: "${filePath}"`)
    }

    try {
      // 使用 fstatSync 从 fd 获取 stat（不可被路径替换攻击影响）
      const fdStat = fs.fstatSync(fd)

      // 第二次 lstat：重新检查路径，与第一次比对 inode
      // 如果攻击者在 open 前将文件替换为符号链接，inode 会不同
      let secondStat: fs.Stats
      try {
        secondStat = fs.lstatSync(resolved)
      } catch {
        throw new Error(
          `Path "${filePath}" was modified during read (TOCTOU detected)`
        )
      }

      // inode 比对：如果路径对应的文件与 fd 打开的文件不是同一个，拒绝读取
      if (
        firstStat.ino !== secondStat.ino ||
        firstStat.ino !== fdStat.ino
      ) {
        throw new Error(
          `Path "${filePath}" was modified during read (TOCTOU detected)`
        )
      }

      if (secondStat.isSymbolicLink()) {
        throw new Error(
          `Path "${filePath}" is a symbolic link, which is not allowed`
        )
      }

      if (!fdStat.isFile()) {
        throw new Error(`Path "${filePath}" is not a file`)
      }

      // Issue 3 修复：使用字节大小而非字符数
      const MAX_BYTES = 100 * 1024

      if (fdStat.size > MAX_BYTES) {
        // 读取前 MAX_BYTES 字节
        const buffer = Buffer.alloc(MAX_BYTES)
        fs.readSync(fd, buffer, 0, MAX_BYTES, 0)
        return buffer.toString('utf-8') + '... (truncated at 100KB)'
      }

      // 文件大小未超限，从 fd 读取
      const content = fs.readFileSync(fd, 'utf-8')
      return content
    } finally {
      fs.closeSync(fd)
    }
  }
}
