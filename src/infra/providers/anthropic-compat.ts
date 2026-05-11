import Anthropic from '@anthropic-ai/sdk'
import type { Message, LLMResponse, StreamEvent, ToolCallData } from '../../types.js'

/**
 * Anthropic 兼容 Provider
 * 处理消息格式转换（system 提取、tool 消息包装）和工具格式转换
 */
export class AnthropicCompatProvider {
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
    const client = new Anthropic({ baseURL: params.baseUrl, apiKey: params.apiKey })

    const { system, messages } = this.convertMessages(params.messages)
    const tools = this.convertTools(params.tools || [])

    const response = await client.messages.create({
      model: params.model,
      max_tokens: 4096,
      system,
      messages,
      tools,
    })

    const content = response.content
      .filter(block => block.type === 'text')
      .map(block => (block as Anthropic.TextBlock).text)
      .join('')

    const toolCalls: ToolCallData[] = response.content
      .filter(block => block.type === 'tool_use')
      .map(block => ({
        id: (block as Anthropic.ToolUseBlock).id,
        name: (block as Anthropic.ToolUseBlock).name,
        arguments: (block as Anthropic.ToolUseBlock).input as Record<string, unknown>,
      }))

    return {
      content,
      tool_calls: toolCalls,
      finish_reason: response.stop_reason || 'end_turn',
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
    const client = new Anthropic({ baseURL: params.baseUrl, apiKey: params.apiKey })

    const { system, messages } = this.convertMessages(params.messages)
    const tools = this.convertTools(params.tools || [])

    const stream = client.messages.stream({
      model: params.model,
      max_tokens: 4096,
      system,
      messages,
      tools,
    })

    // 累积 tool_use block 的 JSON 输入
    const toolCallAccumulator: Map<string, { name: string; inputJson: string }> = new Map()

    for await (const event of stream) {
      if (event.type === 'content_block_start') {
        // 记录 tool_use block 的开始
        if (event.content_block.type === 'tool_use') {
          toolCallAccumulator.set(event.content_block.id, {
            name: event.content_block.name,
            inputJson: '',
          })
        }
      } else if (event.type === 'content_block_delta') {
        if (event.delta.type === 'text_delta') {
          yield { type: 'text_delta', text: event.delta.text }
        } else if (event.delta.type === 'input_json_delta') {
          // 找到当前正在处理的 tool_use block
          // Anthropic 流式事件中，delta 事件的 index 对应 content_block_start 的 index
          // 但我们通过遍历 accumulator 来查找当前活跃的 tool call
          const activeTool = this.findActiveToolCall(toolCallAccumulator)
          if (activeTool) {
            activeTool.inputJson += event.delta.partial_json
          }
        }
      } else if (event.type === 'content_block_stop') {
        // 当前 block 结束，如果是 tool_use 则 flush
        // content_block_stop 没有直接标识是哪个 block，
        // 但我们可以通过检查是否有未完成的 tool call 来判断
      } else if (event.type === 'message_stop') {
        // 消息结束，flush 所有累积的 tool calls
        for (const [id, tc] of toolCallAccumulator) {
          let input: Record<string, unknown> = {}
          try {
            input = JSON.parse(tc.inputJson || '{}')
          } catch {
            input = { _parse_error: tc.inputJson }
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

    // 安全兜底：如果 stream 结束但没有 message_stop 事件
    for (const [id, tc] of toolCallAccumulator) {
      let input: Record<string, unknown> = {}
      try {
        input = JSON.parse(tc.inputJson || '{}')
      } catch {
        input = { _parse_error: tc.inputJson }
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

  /**
   * 找到 accumulator 中最后一个（当前活跃的）tool call
   * Anthropic 流式事件按顺序发送，同一时间只有一个活跃的 tool_use block
   */
  private findActiveToolCall(
    accumulator: Map<string, { name: string; inputJson: string }>,
  ): { name: string; inputJson: string } | undefined {
    let last: { name: string; inputJson: string } | undefined
    for (const value of accumulator.values()) {
      last = value
    }
    return last
  }

  /**
   * 将内部 Message 格式转换为 Anthropic API 格式
   * - system 消息提取为顶层参数
   * - tool 消息转换为 user 消息 + tool_result content block
   * - assistant+tool_calls 转换为 assistant 消息 + tool_use content blocks
   */
  private convertMessages(messages: Message[]): {
    system: string
    messages: Anthropic.MessageParam[]
  } {
    let system = ''
    const convertedMessages: Anthropic.MessageParam[] = []

    for (const msg of messages) {
      if (msg.role === 'system') {
        system = msg.content
      } else if (msg.role === 'user') {
        convertedMessages.push({ role: 'user', content: msg.content })
      } else if (msg.role === 'assistant') {
        if (msg.tool_calls && msg.tool_calls.length > 0) {
          const content: Anthropic.ContentBlockParam[] = [
            { type: 'text', text: msg.content || '' },
            ...msg.tool_calls.map(tc => ({
              type: 'tool_use' as const,
              id: tc.id,
              name: tc.name,
              input: tc.arguments,
            })),
          ]
          convertedMessages.push({ role: 'assistant', content })
        } else {
          convertedMessages.push({ role: 'assistant', content: msg.content })
        }
      } else if (msg.role === 'tool') {
        convertedMessages.push({
          role: 'user',
          content: [
            {
              type: 'tool_result' as const,
              tool_use_id: msg.tool_call_id || '',
              content: msg.content,
            },
          ],
        })
      }
    }

    return { system, messages: convertedMessages }
  }

  /**
   * 将 OpenAI function 格式转换为 Anthropic input_schema 格式
   */
  private convertTools(tools: Record<string, unknown>[]): Anthropic.Tool[] {
    return tools.map(tool => {
      if (tool.type === 'function' && tool.function) {
        const fn = tool.function as Record<string, unknown>
        return {
          name: fn.name as string,
          description: fn.description as string,
          input_schema: fn.parameters as Anthropic.Tool.InputSchema,
        }
      }
      return tool as unknown as Anthropic.Tool
    })
  }
}
