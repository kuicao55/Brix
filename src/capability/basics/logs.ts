/**
 * 日志查询工具 — 从 JSONL flow log 中读取和格式化日志
 */

import { readAll, readEntry, formatDetail } from '../../log/writer.js'

/**
 * 获取最近 N 条日志条目
 */
export function getRecentLogs(filePath: string, count: number = 10): Record<string, unknown>[] {
  const entries = readAll(filePath)
  return entries.slice(-count)
}

/**
 * 获取指定 traceId 的格式化日志详情
 */
export function getLogDetail(filePath: string, traceId: string): string | null {
  const entry = readEntry(filePath, traceId)
  if (!entry) return null
  return formatDetail(entry)
}
