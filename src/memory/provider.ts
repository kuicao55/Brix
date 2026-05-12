/**
 * MemoryProvider 工厂 — 基于文件系统的 MemoryProvider 实现
 *
 * 读写 data_dir 目录下的文件:
 *   - soul.md     → loadSoul()
 *   - user.md     → loadUserMemory()
 *   - sessions/   → listSessions(), resumeSession(), addMessage(), saveSession()
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
  const sessionsDir = path.join(resolvedDir, 'sessions')

  // 确保数据目录存在
  fs.mkdirSync(resolvedDir, { recursive: true })
  fs.mkdirSync(sessionsDir, { recursive: true })

  // 当前活跃会话状态
  let currentSessionId: string | null = null
  let currentMessages: Array<{ role: string; content: string; timestamp: string }> = []

  function safeRead(filePath: string): string {
    try {
      return fs.readFileSync(filePath, 'utf-8')
    } catch {
      return ''
    }
  }

  function readIndex(): SessionIndexEntry[] {
    const indexPath = path.join(sessionsDir, 'index.json')
    try {
      return JSON.parse(fs.readFileSync(indexPath, 'utf-8')) as SessionIndexEntry[]
    } catch {
      return []
    }
  }

  function writeIndex(entries: SessionIndexEntry[]): void {
    const indexPath = path.join(sessionsDir, 'index.json')
    fs.writeFileSync(indexPath, JSON.stringify(entries, null, 2), 'utf-8')
  }

  function generateId(): string {
    return crypto.randomUUID()
  }

  return {
    loadSoul(): string {
      return safeRead(path.join(resolvedDir, 'soul.md'))
    },

    loadUserMemory(): string {
      return safeRead(path.join(resolvedDir, 'user.md'))
    },

    listSessions(): SessionIndexEntry[] {
      // 按更新时间倒序排列（最新在前）
      return readIndex().sort((a, b) => (b.updated ?? '').localeCompare(a.updated ?? ''))
    },

    async resumeSession(sessionId: string): Promise<void> {
      const sessions = readIndex()
      const match = sessions.find(s => s.id === sessionId)
      if (!match) {
        throw new Error(`Session not found: ${sessionId}`)
      }

      // 加载会话消息
      const sessionFile = path.join(sessionsDir, `session-${sessionId}.json`)
      try {
        const raw = fs.readFileSync(sessionFile, 'utf-8')
        currentMessages = JSON.parse(raw)
      } catch {
        currentMessages = []
      }
      currentSessionId = sessionId
    },

    addMessage(role: string, content: string): void {
      // 如果没有活跃会话，创建新会话
      if (!currentSessionId) {
        currentSessionId = generateId()
        currentMessages = []
      }

      currentMessages.push({
        role,
        content,
        timestamp: new Date().toISOString(),
      })
    },

    saveSession(): void {
      if (!currentSessionId || currentMessages.length === 0) return

      // 写入消息文件
      const sessionFile = path.join(sessionsDir, `session-${currentSessionId}.json`)
      fs.writeFileSync(sessionFile, JSON.stringify(currentMessages, null, 2), 'utf-8')

      // 更新索引
      const sessions = readIndex()
      const existing = sessions.findIndex(s => s.id === currentSessionId)

      const now = new Date().toISOString()
      const userMsgs = currentMessages.filter(m => m.role === 'user')
      const preview = userMsgs.length > 0
        ? userMsgs[userMsgs.length - 1].content.slice(0, 100).replace(/\n/g, ' ')
        : ''

      const entry: SessionIndexEntry = {
        id: currentSessionId,
        created: existing >= 0 ? sessions[existing].created : now,
        updated: now,
        message_count: currentMessages.length,
        preview,
      }

      if (existing >= 0) {
        sessions[existing] = entry
      } else {
        sessions.unshift(entry)
      }

      writeIndex(sessions)
    },

    clearSession(): void {
      currentSessionId = null
      currentMessages = []
    },
  }
}
