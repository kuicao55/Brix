/**
 * Memory 文件访问工具 — 加载 soul.md 和 user.md 内容
 */

import type { MemoryProvider } from '../../memory/types.js'

/**
 * 加载 soul.md 内容
 */
export function loadSoul(memory: MemoryProvider): string {
  return memory.loadSoul()
}

/**
 * 加载 user.md 内容
 */
export function loadUser(memory: MemoryProvider): string {
  return memory.loadUserMemory()
}
