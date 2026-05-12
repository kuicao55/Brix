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
 * 格式化单条日志条目为可读文本（匹配 Python format_detail）
 */
export function formatDetail(entry: Record<string, unknown>): string {
  const ts = entry.ts ?? '?'
  const trace = entry.trace ?? '?'
  const inp = entry.input ?? ''
  const model = entry.model ?? '?'
  const msTotal = entry.ms_total ?? 0
  const llmCalls = entry.llm_calls ?? 0
  const tools = entry.tools ?? 0
  const iters = entry.iters ?? 0
  const error = entry.error
  const steps = Array.isArray(entry.steps) ? entry.steps : []
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

  // 步骤描述（匹配 Python 版本）
  const desc: Record<string, string> = {
    memory: '从存储加载历史记录，裁剪上下文窗口',
    intent: '调用 LLM 分类用户意图 (chat/task/tool_use)',
    complexity: '基于关键词规则评估请求复杂度',
    router: '根据意图和复杂度选择最佳模型',
    orch_plan: '调用 LLM 生成回复 (streaming)',
    tool_exec: '执行工具调用并返回结果',
    persist: '将本轮对话保存到存储',
  }

  // 逐步骤详情
  for (let i = 0; i < steps.length; i++) {
    const s = steps[i] as Record<string, unknown>
    const m = s.m ?? '?'
    const at = s.at ?? ''
    const atStr = at ? `  @${at}` : ''
    lines.push(`  [${i + 1}] ${m}${atStr}`)

    const d = desc[String(m)]
    if (d) {
      lines.push(`      ${d}`)
    }

    for (const [k, v] of Object.entries(s)) {
      if (k === 'm' || k === 'at') continue
      lines.push(`      ${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
    }
    lines.push('')
  }

  if (error) {
    lines.push(`  ERROR: ${error}`)
    lines.push('')
  }

  lines.push(sep)
  lines.push(
    `  Total: ${msTotal}ms | LLM calls: ${llmCalls} | Tools: ${tools} | Iterations: ${iters}`
  )
  lines.push(sep)

  return lines.join('\n')
}
