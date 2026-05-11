import { describe, expect, it, mock } from 'bun:test'

// Mock Anthropic SDK — 使用可配置的 handler 支持不同测试场景
type MockCreateHandler = (params: Record<string, unknown>) => unknown
type MockStreamHandler = (params: Record<string, unknown>) => unknown

let mockCreateHandler: MockCreateHandler = () => {
  return Promise.resolve({
    content: [{ type: 'text', text: 'Hello!' }],
    stop_reason: 'end_turn',
  })
}

let mockStreamHandler: MockStreamHandler = () => {
  return (async function* () {
    yield { type: 'content_block_start', content_block: { type: 'text', text: '' }, index: 0 }
    yield { type: 'content_block_delta', delta: { type: 'text_delta', text: 'Hi' }, index: 0 }
    yield { type: 'content_block_stop', index: 0 }
    yield { type: 'message_stop' }
  })()
}

mock.module('@anthropic-ai/sdk', () => ({
  default: class MockAnthropic {
    constructor(_params: Record<string, unknown>) {}
    messages = {
      create: (params: Record<string, unknown>) => mockCreateHandler(params),
      stream: (params: Record<string, unknown>) => {
        const gen = mockStreamHandler(params)
        // Anthropic SDK 的 stream 返回一个可迭代对象
        return {
          [Symbol.asyncIterator]: () => gen,
        }
      },
    }
  },
}))

const { AnthropicCompatProvider } = await import('../src/infra/providers/anthropic-compat.js')

describe('AnthropicCompatProvider', () => {
  const provider = new AnthropicCompatProvider()

  describe('chat', () => {
    it('应该返回 LLMResponse 格式的响应', async () => {
      mockCreateHandler = () =>
        Promise.resolve({
          content: [{ type: 'text', text: 'Hello!' }],
          stop_reason: 'end_turn',
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(result).toHaveProperty('content')
      expect(result).toHaveProperty('tool_calls')
      expect(result).toHaveProperty('finish_reason')
      expect(typeof result.content).toBe('string')
      expect(Array.isArray(result.tool_calls)).toBe(true)
      expect(typeof result.finish_reason).toBe('string')
    })

    it('content 应该正确拼接多个 text block', async () => {
      mockCreateHandler = () =>
        Promise.resolve({
          content: [
            { type: 'text', text: 'Hello ' },
            { type: 'text', text: 'world!' },
          ],
          stop_reason: 'end_turn',
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(result.content).toBe('Hello world!')
    })

    it('finish_reason 应该映射 stop_reason', async () => {
      mockCreateHandler = () =>
        Promise.resolve({
          content: [{ type: 'text', text: 'Hello!' }],
          stop_reason: 'end_turn',
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(result.finish_reason).toBe('end_turn')
    })

    it('应该提取 tool_use block 为 ToolCallData', async () => {
      mockCreateHandler = () =>
        Promise.resolve({
          content: [
            { type: 'text', text: 'I will search.' },
            {
              type: 'tool_use',
              id: 'toolu_123',
              name: 'web_search',
              input: { query: 'test query' },
            },
          ],
          stop_reason: 'tool_use',
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Search for test' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(result.content).toBe('I will search.')
      expect(result.tool_calls).toHaveLength(1)
      expect(result.tool_calls[0]).toEqual({
        id: 'toolu_123',
        name: 'web_search',
        arguments: { query: 'test query' },
      })
      expect(result.finish_reason).toBe('tool_use')
    })

    it('应该处理多个 tool_use blocks', async () => {
      mockCreateHandler = () =>
        Promise.resolve({
          content: [
            {
              type: 'tool_use',
              id: 'toolu_1',
              name: 'tool_a',
              input: { x: 1 },
            },
            {
              type: 'tool_use',
              id: 'toolu_2',
              name: 'tool_b',
              input: { y: 2 },
            },
          ],
          stop_reason: 'tool_use',
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Do two things' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(result.tool_calls).toHaveLength(2)
      expect(result.tool_calls[0].name).toBe('tool_a')
      expect(result.tool_calls[1].name).toBe('tool_b')
    })

    it('stop_reason 为 null 时应返回 end_turn', async () => {
      mockCreateHandler = () =>
        Promise.resolve({
          content: [{ type: 'text', text: 'Hi' }],
          stop_reason: null,
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hello' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(result.finish_reason).toBe('end_turn')
    })
  })

  describe('消息转换', () => {
    it('应该将 system 消息提取为顶层 system 参数', async () => {
      let capturedParams: Record<string, unknown> = {}
      mockCreateHandler = (params) => {
        capturedParams = params
        return Promise.resolve({
          content: [{ type: 'text', text: 'OK' }],
          stop_reason: 'end_turn',
        })
      }

      await provider.chat({
        messages: [
          { role: 'system', content: 'You are helpful.' },
          { role: 'user', content: 'Hi' },
        ],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(capturedParams.system).toBe('You are helpful.')
      // system 不应出现在 messages 数组中
      const msgs = capturedParams.messages as Array<Record<string, unknown>>
      expect(msgs).toHaveLength(1)
      expect(msgs[0].role).toBe('user')
    })

    it('应该将 assistant+tool_calls 转换为 Anthropic content block 格式', async () => {
      let capturedParams: Record<string, unknown> = {}
      mockCreateHandler = (params) => {
        capturedParams = params
        return Promise.resolve({
          content: [{ type: 'text', text: 'Done' }],
          stop_reason: 'end_turn',
        })
      }

      await provider.chat({
        messages: [
          { role: 'user', content: 'Search' },
          {
            role: 'assistant',
            content: 'Let me search.',
            tool_calls: [
              { id: 'toolu_1', name: 'search', arguments: { q: 'test' } },
            ],
          },
          {
            role: 'tool',
            content: 'Search results here',
            tool_call_id: 'toolu_1',
          },
          { role: 'user', content: 'Thanks' },
        ],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      const msgs = capturedParams.messages as Array<Record<string, unknown>>
      // assistant 消息应该包含 content blocks
      const assistantMsg = msgs[1]
      expect(assistantMsg.role).toBe('assistant')
      const content = assistantMsg.content as Array<Record<string, unknown>>
      expect(content).toHaveLength(2)
      expect(content[0]).toEqual({ type: 'text', text: 'Let me search.' })
      expect(content[1]).toEqual({
        type: 'tool_use',
        id: 'toolu_1',
        name: 'search',
        input: { q: 'test' },
      })
    })

    it('应该将 tool 结果转换为 user 消息 + tool_result content block', async () => {
      let capturedParams: Record<string, unknown> = {}
      mockCreateHandler = (params) => {
        capturedParams = params
        return Promise.resolve({
          content: [{ type: 'text', text: 'Done' }],
          stop_reason: 'end_turn',
        })
      }

      await provider.chat({
        messages: [
          { role: 'user', content: 'Search' },
          {
            role: 'assistant',
            content: '',
            tool_calls: [
              { id: 'toolu_1', name: 'search', arguments: { q: 'test' } },
            ],
          },
          {
            role: 'tool',
            content: 'Search results here',
            tool_call_id: 'toolu_1',
          },
        ],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      const msgs = capturedParams.messages as Array<Record<string, unknown>>
      // tool 结果应该作为 user 消息
      const toolResultMsg = msgs[2]
      expect(toolResultMsg.role).toBe('user')
      const content = toolResultMsg.content as Array<Record<string, unknown>>
      expect(content).toHaveLength(1)
      expect(content[0]).toEqual({
        type: 'tool_result',
        tool_use_id: 'toolu_1',
        content: 'Search results here',
      })
    })

    it('没有 system 消息时 system 应为空字符串', async () => {
      let capturedParams: Record<string, unknown> = {}
      mockCreateHandler = (params) => {
        capturedParams = params
        return Promise.resolve({
          content: [{ type: 'text', text: 'OK' }],
          stop_reason: 'end_turn',
        })
      }

      await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(capturedParams.system).toBe('')
    })
  })

  describe('工具格式转换', () => {
    it('应该将 OpenAI function 格式转换为 Anthropic input_schema 格式', async () => {
      let capturedParams: Record<string, unknown> = {}
      mockCreateHandler = (params) => {
        capturedParams = params
        return Promise.resolve({
          content: [{ type: 'text', text: 'OK' }],
          stop_reason: 'end_turn',
        })
      }

      await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        tools: [
          {
            type: 'function',
            function: {
              name: 'web_search',
              description: 'Search the web',
              parameters: {
                type: 'object',
                properties: {
                  query: { type: 'string' },
                },
                required: ['query'],
              },
            },
          },
        ],
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      const tools = capturedParams.tools as Array<Record<string, unknown>>
      expect(tools).toHaveLength(1)
      expect(tools[0]).toEqual({
        name: 'web_search',
        description: 'Search the web',
        input_schema: {
          type: 'object',
          properties: {
            query: { type: 'string' },
          },
          required: ['query'],
        },
      })
    })

    it('没有 tools 参数时应传空数组', async () => {
      let capturedParams: Record<string, unknown> = {}
      mockCreateHandler = (params) => {
        capturedParams = params
        return Promise.resolve({
          content: [{ type: 'text', text: 'OK' }],
          stop_reason: 'end_turn',
        })
      }

      await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(capturedParams.tools).toEqual([])
    })
  })

  describe('chatStream', () => {
    it('应该返回 AsyncGenerator', async () => {
      mockStreamHandler = () =>
        (async function* () {
          yield { type: 'content_block_start', content_block: { type: 'text', text: '' }, index: 0 }
          yield { type: 'content_block_delta', delta: { type: 'text_delta', text: 'Hi' }, index: 0 }
          yield { type: 'content_block_stop', index: 0 }
          yield { type: 'message_stop' }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      expect(stream[Symbol.asyncIterator]).toBeDefined()
    })

    it('应该产出 text_delta 事件', async () => {
      mockStreamHandler = () =>
        (async function* () {
          yield { type: 'content_block_start', content_block: { type: 'text', text: '' }, index: 0 }
          yield { type: 'content_block_delta', delta: { type: 'text_delta', text: 'Hello ' }, index: 0 }
          yield { type: 'content_block_delta', delta: { type: 'text_delta', text: 'world!' }, index: 0 }
          yield { type: 'content_block_stop', index: 0 }
          yield { type: 'message_stop' }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      const events = []
      for await (const event of stream) {
        events.push(event)
      }

      const textEvents = events.filter((e) => e.type === 'text_delta')
      expect(textEvents).toHaveLength(2)
      expect(textEvents[0]).toEqual({ type: 'text_delta', text: 'Hello ' })
      expect(textEvents[1]).toEqual({ type: 'text_delta', text: 'world!' })
    })

    it('应该在 content_block_stop 时 flush tool_use block', async () => {
      mockStreamHandler = () =>
        (async function* () {
          // tool_use block 开始
          yield {
            type: 'content_block_start',
            content_block: { type: 'tool_use', id: 'toolu_1', name: 'search' },
            index: 1,
          }
          // input JSON 分片到达
          yield {
            type: 'content_block_delta',
            delta: { type: 'input_json_delta', partial_json: '{"query":' },
            index: 1,
          }
          yield {
            type: 'content_block_delta',
            delta: { type: 'input_json_delta', partial_json: '"test"}' },
            index: 1,
          }
          // block 结束 — 应该 flush tool call
          yield { type: 'content_block_stop', index: 1 }
          yield { type: 'message_stop' }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      const events = []
      for await (const event of stream) {
        events.push(event)
      }

      const toolEvents = events.filter((e) => e.type === 'tool_call')
      expect(toolEvents).toHaveLength(1)
      expect(toolEvents[0]).toEqual({
        type: 'tool_call',
        id: 'toolu_1',
        name: 'search',
        input: { query: 'test' },
      })
    })

    it('应该处理流式 tool call 中的畸形 JSON', async () => {
      mockStreamHandler = () =>
        (async function* () {
          yield {
            type: 'content_block_start',
            content_block: { type: 'tool_use', id: 'toolu_1', name: 'search' },
            index: 1,
          }
          yield {
            type: 'content_block_delta',
            delta: { type: 'input_json_delta', partial_json: '{invalid json' },
            index: 1,
          }
          yield { type: 'content_block_stop', index: 1 }
          yield { type: 'message_stop' }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'claude-3-5-sonnet-20241022',
        baseUrl: 'https://api.anthropic.com',
        apiKey: 'test-key',
      })

      const events = []
      for await (const event of stream) {
        events.push(event)
      }

      const toolEvents = events.filter((e) => e.type === 'tool_call')
      expect(toolEvents).toHaveLength(1)
      expect(toolEvents[0]).toEqual({
        type: 'tool_call',
        id: 'toolu_1',
        name: 'search',
        input: { _parse_error: '{invalid json' },
      })
    })
  })

  describe('类型结构', () => {
    it('provider 应该有 chat 和 chatStream 方法', () => {
      expect(typeof provider.chat).toBe('function')
      expect(typeof provider.chatStream).toBe('function')
    })
  })
})
