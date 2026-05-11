import OpenAI from 'openai'
import type { Message, LLMResponse, StreamEvent, ToolCallData } from '../../types.js'

/**
 * OpenAI 兼容 Provider
 * 支持所有 OpenAI API 兼容的端点（OpenAI、DeepSeek、Moonshot 等）
 */
export class OpenAICompatProvider {
  /**
   * 非流式 chat 请求
   */
  async chat(params: {
    messages: Message[]
    model: string
    tools?: Record<string, unknown>[]
    baseUrl: string
    apiKey: string
  }): Promise<LLMResponse> {
    const client = new OpenAI({ baseURL: params.baseUrl, apiKey: params.apiKey })

    const response = await client.chat.completions.create({
      model: params.model,
      messages: params.messages as OpenAI.ChatCompletionMessageParam[],
      tools: params.tools as unknown as OpenAI.ChatCompletionTool[],
    })

    const choice = response.choices[0]
    const toolCalls: ToolCallData[] = (choice.message.tool_calls || []).map(tc => {
      let args: Record<string, unknown> = {}
      try {
        args = JSON.parse(tc.function.arguments)
      } catch {
        args = { _parse_error: tc.function.arguments }
      }
      return {
        id: tc.id,
        name: tc.function.name,
        arguments: args,
      }
    })

    return {
      content: choice.message.content || '',
      tool_calls: toolCalls,
      finish_reason: choice.finish_reason || 'stop',
    }
  }

  /**
   * 流式 chat 请求 — 产出 StreamEvent
   */
  async *chatStream(params: {
    messages: Message[]
    model: string
    tools?: Record<string, unknown>[]
    baseUrl: string
    apiKey: string
  }): AsyncGenerator<StreamEvent> {
    const client = new OpenAI({ baseURL: params.baseUrl, apiKey: params.apiKey })

    const stream = await client.chat.completions.create({
      model: params.model,
      messages: params.messages as OpenAI.ChatCompletionMessageParam[],
      tools: params.tools as unknown as OpenAI.ChatCompletionTool[],
      stream: true,
    })

    const toolCallAccumulator: Map<string, { name: string; arguments: string }> = new Map()

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta
      if (!delta) continue

      if (delta.content) {
        yield { type: 'text_delta', text: delta.content }
      }

      if (delta.tool_calls) {
        for (const tc of delta.tool_calls) {
          const existing = toolCallAccumulator.get(tc.id || '') || { name: '', arguments: '' }
          if (tc.function?.name) existing.name = tc.function.name
          if (tc.function?.arguments) existing.arguments += tc.function.arguments
          toolCallAccumulator.set(tc.id || '', existing)
        }
      }

      if (chunk.choices[0]?.finish_reason === 'tool_calls') {
        for (const [id, tc] of toolCallAccumulator) {
          let input: Record<string, unknown> = {}
          try {
            input = JSON.parse(tc.arguments)
          } catch {
            input = { _parse_error: tc.arguments }
          }
          yield {
            type: 'tool_call',
            id,
            name: tc.name,
            input,
          }
        }
        toolCallAccumulator.clear()
      }
    }

    // flush 累积的 tool calls（stream 可能以 stop 或其他 finish_reason 结束）
    for (const [id, tc] of toolCallAccumulator) {
      let input: Record<string, unknown> = {}
      try {
        input = JSON.parse(tc.arguments)
      } catch {
        input = { _parse_error: tc.arguments }
      }
      yield {
        type: 'tool_call',
        id,
        name: tc.name,
        input,
      }
    }
    toolCallAccumulator.clear()
  }
}
