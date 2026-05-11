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
}
