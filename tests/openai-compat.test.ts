import { describe, expect, it, mock } from 'bun:test'

// Mock OpenAI SDK — 使用可配置的 handler 支持不同测试场景
type MockHandler = (params: Record<string, unknown>) => unknown
let mockHandler: MockHandler = () => {
  // 默认: 非流式简单响应
  return Promise.resolve({
    choices: [
      {
        message: { content: 'Hello!', tool_calls: undefined },
        finish_reason: 'stop',
      },
    ],
  })
}

mock.module('openai', () => ({
  default: class MockOpenAI {
    chat = {
      completions: {
        create: (params: Record<string, unknown>) => mockHandler(params),
      },
    }
  },
}))

const { OpenAICompatProvider } = await import('../src/infra/providers/openai-compat.js')

describe('OpenAICompatProvider', () => {
  const provider = new OpenAICompatProvider()

  describe('chat', () => {
    it('应该返回 LLMResponse 格式的响应', async () => {
      mockHandler = () =>
        Promise.resolve({
          choices: [
            {
              message: { content: 'Hello!', tool_calls: undefined },
              finish_reason: 'stop',
            },
          ],
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(result).toHaveProperty('content')
      expect(result).toHaveProperty('tool_calls')
      expect(result).toHaveProperty('finish_reason')
      expect(typeof result.content).toBe('string')
      expect(Array.isArray(result.tool_calls)).toBe(true)
      expect(typeof result.finish_reason).toBe('string')
    })

    it('content 应该是字符串', async () => {
      mockHandler = () =>
        Promise.resolve({
          choices: [
            {
              message: { content: 'Hello!', tool_calls: undefined },
              finish_reason: 'stop',
            },
          ],
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(result.content).toBe('Hello!')
    })

    it('finish_reason 应该是 stop', async () => {
      mockHandler = () =>
        Promise.resolve({
          choices: [
            {
              message: { content: 'Hello!', tool_calls: undefined },
              finish_reason: 'stop',
            },
          ],
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(result.finish_reason).toBe('stop')
    })

    it('应该处理 tool_calls 参数中的畸形 JSON', async () => {
      mockHandler = () =>
        Promise.resolve({
          choices: [
            {
              message: {
                content: '',
                tool_calls: [
                  {
                    id: 'call_1',
                    function: {
                      name: 'test_tool',
                      arguments: '{invalid json!!!',
                    },
                  },
                ],
              },
              finish_reason: 'tool_calls',
            },
          ],
        })

      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(result.tool_calls).toHaveLength(1)
      expect(result.tool_calls[0].id).toBe('call_1')
      expect(result.tool_calls[0].name).toBe('test_tool')
      expect(result.tool_calls[0].arguments).toEqual({ _parse_error: '{invalid json!!!' })
    })
  })

  describe('chatStream', () => {
    it('应该返回 AsyncGenerator', async () => {
      mockHandler = () =>
        (async function* () {
          yield { choices: [{ delta: { content: 'Hi' }, finish_reason: null }] }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(stream[Symbol.asyncIterator]).toBeDefined()
    })

    it('应该产出 text_delta 事件', async () => {
      mockHandler = () =>
        (async function* () {
          yield { choices: [{ delta: { content: 'Hello ' }, finish_reason: null }] }
          yield { choices: [{ delta: { content: 'world!' }, finish_reason: null }] }
          yield { choices: [{ delta: {}, finish_reason: 'stop' }] }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      const events = []
      for await (const event of stream) {
        events.push(event)
      }

      expect(events.length).toBe(2)
      expect(events[0]).toEqual({ type: 'text_delta', text: 'Hello ' })
      expect(events[1]).toEqual({ type: 'text_delta', text: 'world!' })
    })

    it('应该处理流式 tool_call 中的畸形 JSON', async () => {
      mockHandler = () =>
        (async function* () {
          yield {
            choices: [
              {
                delta: {
                  tool_calls: [
                    { id: 'call_1', function: { name: 'test_tool', arguments: '{bad' } },
                  ],
                },
                finish_reason: null,
              },
            ],
          }
          yield {
            choices: [
              {
                delta: {
                  tool_calls: [
                    { id: 'call_1', function: { arguments: ' json!!!' } },
                  ],
                },
                finish_reason: null,
              },
            ],
          }
          // finish_reason === 'tool_calls' 触发 flush
          yield {
            choices: [{ delta: {}, finish_reason: 'tool_calls' }],
          }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
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
        id: 'call_1',
        name: 'test_tool',
        input: { _parse_error: '{bad json!!!' },
      })
    })

    it('应该在 stream 结束时 flush 累积的 tool calls（无 tool_calls finish_reason）', async () => {
      mockHandler = () =>
        (async function* () {
          yield {
            choices: [
              {
                delta: {
                  tool_calls: [
                    { id: 'call_1', function: { name: 'tool_a', arguments: '{"x":1}' } },
                  ],
                },
                finish_reason: null,
              },
            ],
          }
          yield {
            choices: [
              {
                delta: {
                  tool_calls: [
                    { id: 'call_2', function: { name: 'tool_b', arguments: '{"y":2}' } },
                  ],
                },
                finish_reason: null,
              },
            ],
          }
          // stream 以 stop 结束，不是 tool_calls
          yield { choices: [{ delta: {}, finish_reason: 'stop' }] }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      const events = []
      for await (const event of stream) {
        events.push(event)
      }

      const toolEvents = events.filter((e) => e.type === 'tool_call')
      expect(toolEvents).toHaveLength(2)
      expect(toolEvents[0]).toEqual({
        type: 'tool_call',
        id: 'call_1',
        name: 'tool_a',
        input: { x: 1 },
      })
      expect(toolEvents[1]).toEqual({
        type: 'tool_call',
        id: 'call_2',
        name: 'tool_b',
        input: { y: 2 },
      })
    })

    it('应该在 stream 结束时 flush 累积的畸形 JSON tool calls', async () => {
      mockHandler = () =>
        (async function* () {
          yield {
            choices: [
              {
                delta: {
                  tool_calls: [
                    { id: 'call_1', function: { name: 'tool_a', arguments: '{broken' } },
                  ],
                },
                finish_reason: null,
              },
            ],
          }
          // stream 以 stop 结束
          yield { choices: [{ delta: {}, finish_reason: 'stop' }] }
        })()

      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
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
        id: 'call_1',
        name: 'tool_a',
        input: { _parse_error: '{broken' },
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
