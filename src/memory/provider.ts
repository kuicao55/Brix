/**
 * MemoryProvider 工厂 — 基于文件系统的 MemoryProvider 实现
 *
 * 读写 data_dir 目录下的文件:
 *   - soul.md     → loadSoul()
 *   - user.md     → loadUserMemory()
 *   - sessions/   → listSessions(), resumeSession()
 */

import * as fs from 'node:fs'
import * as path from 'node:path'
import type { MemoryProvider } from './types.js'
import type { SessionIndexEntry } from '../types.js'

/**
 * 创建基于文件系统的 MemoryProvider
 * @param dataDir - 数据目录路径（相对或绝对）
 * @param maxContextTokens - 最大上下文 token 数（预留，当前未使用）
 * @returns MemoryProvider 实例
 */
export function createMemoryProvider(dataDir: string, _maxContextTokens?: number): MemoryProvider {
  const resolvedDir = path.resolve(dataDir)

  // 确保数据目录存在
  fs.mkdirSync(resolvedDir, { recursive: true })
  fs.mkdirSync(path.join(resolvedDir, 'sessions'), { recursive: true })

  function safeRead(filePath: string): string {
    try {
      return fs.readFileSync(filePath, 'utf-8')
    } catch {
      return ''
    }
  }

  return {
    loadSoul(): string {
      return safeRead(path.join(resolvedDir, 'soul.md'))
    },

    loadUserMemory(): string {
      return safeRead(path.join(resolvedDir, 'user.md'))
    },

    listSessions(): SessionIndexEntry[] {
      const indexPath = path.join(resolvedDir, 'sessions', 'index.json')
      try {
        const content = fs.readFileSync(indexPath, 'utf-8')
        return JSON.parse(content) as SessionIndexEntry[]
      } catch {
        return []
      }
    },

    async resumeSession(sessionId: string): Promise<void> {
      const sessions = (() => {
        const indexPath = path.join(resolvedDir, 'sessions', 'index.json')
        try {
          const content = fs.readFileSync(indexPath, 'utf-8')
          return JSON.parse(content) as SessionIndexEntry[]
        } catch {
          return [] as SessionIndexEntry[]
        }
      })()

      if (!sessions.find(s => s.id === sessionId)) {
        throw new Error(`Session not found: ${sessionId}`)
      }
    },
  }
}
