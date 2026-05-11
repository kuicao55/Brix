/**
 * JSONL 日志读取工具 — flow log 的文件 I/O 层
 * 从 JSONL 文件中读取和格式化日志条目
 */

import { readFileSync, existsSync } from 'fs'

/**
 * 读取 JSONL 文件中的所有条目
 */
export function readAll(filePath: string): Record<string, unknown>[] {
  if (!existsSync(filePath)) return []
  const content = readFileSync(filePath, 'utf-8')
  const entries: Record<string, unknown>[] = []
  for (const line of content.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    try {
      entries.push(JSON.parse(trimmed))
    } catch {
      continue
    }
  }
  return entries
}

/**
 * 按 trace ID 读取单条日志，未找到返回 null
 */
export function readEntry(filePath: string, traceId: string): Record<string, unknown> | null {
  const entries = readAll(filePath)
  return entries.find(e => e.trace === traceId) ?? null
}

/**
 * 格式化单条日志条目为可读文本
 */
export function formatDetail(entry: Record<string, unknown>): string {
  const ts = entry.ts ?? '?'
  const trace = entry.trace ?? '?'
  const inp = entry.input ?? ''
  const model = entry.model ?? '?'
  const msTotal = entry.ms_total ?? 0
  const error = entry.error
  const status = error ? 'ERR' : 'OK'
  const sep = '-'.repeat(60)

  const lines = [
    sep,
    `  Trace:  ${trace}`,
    `  Time:   ${ts}`,
    `  Input:  ${inp}`,
    `  Model:  ${model}`,
    `  Status: ${status}`,
    sep,
  ]

  if (error) {
    lines.push(`  ERROR: ${error}`)
    lines.push('')
  }

  lines.push(sep)
  lines.push(`  Total: ${msTotal}ms`)
  lines.push(sep)

  return lines.join('\n')
}
