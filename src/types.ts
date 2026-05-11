/** 消息格式 — 贯穿 memory/orchestrator/infra 层 */
export type Message = {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  tool_calls?: ToolCallData[]
  tool_call_id?: string
  tool_name?: string
  timestamp?: string
}

/** LLM 返回的工具调用 */
export type ToolCallData = {
  id: string
  name: string
  arguments: Record<string, unknown>
}

/** LLM 响应 */
export type LLMResponse = {
  content: string
  tool_calls: ToolCallData[]
  finish_reason: string
}

/** 流式事件 */
export type StreamEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'tool_call'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; id: string; name: string; result: string; ms: number; is_error: boolean }

/** 会话索引条目 */
export type SessionIndexEntry = {
  id: string
  created: string
  updated: string
  message_count: number
  preview: string
}

/** Hook 事件 */
export type HookEvent = {
  name: string
  data: Record<string, unknown>
}
