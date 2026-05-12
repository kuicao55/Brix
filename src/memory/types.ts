/**
 * MemoryProvider 接口 — memory 层的核心协议
 * 所有 memory 实现必须满足此接口
 */

import type { SessionIndexEntry } from '../types.js'

export interface MemoryProvider {
  /** 加载 soul.md 内容 */
  loadSoul(): string

  /** 加载 user.md 内容 */
  loadUserMemory(): string

  /** 列出所有会话索引（最新在前） */
  listSessions(): SessionIndexEntry[]

  /** 恢复指定会话为当前活跃会话 */
  resumeSession(sessionId: string): Promise<void>

  /** 添加消息到当前活跃会话 */
  addMessage(role: string, content: string): void

  /** 保存当前活跃会话到磁盘 */
  saveSession(): void

  /** 清除当前活跃会话（开始新会话） */
  clearSession(): void
}
