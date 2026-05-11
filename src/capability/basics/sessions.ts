/**
 * 会话管理工具 — 列出、匹配、恢复会话
 */

import type { MemoryProvider } from '../../memory/types.js'
import type { SessionIndexEntry } from '../../types.js'

/**
 * 列出所有会话索引
 */
export function listSessions(memory: MemoryProvider): SessionIndexEntry[] {
  return memory.listSessions()
}

/**
 * 按前缀匹配唯一会话；多个匹配或无匹配时返回 null
 */
export function get_session_by_prefix(memory: MemoryProvider, prefix: string): SessionIndexEntry | null {
  const sessions = memory.listSessions()
  const matches = sessions.filter(s => s.id.startsWith(prefix))
  return matches.length === 1 ? matches[0] : null
}

/**
 * 恢复指定会话；sessionId 无效时返回 false
 */
export async function resumeSession(memory: MemoryProvider, sessionId: string): Promise<boolean> {
  const sessions = memory.listSessions()
  const session = sessions.find(s => s.id === sessionId)
  if (!session) return false
  await memory.resumeSession(sessionId)
  return true
}
