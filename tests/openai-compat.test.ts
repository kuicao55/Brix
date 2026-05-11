import { describe, expect, it, mock } from 'bun:test'

// Mock OpenAI SDK — 区分流式和非流式调用
const mockCreate = mock((params: Record<string, unknown>) => {
  if (params.stream) {
    return (async function* () {
      yield {
        choices: [
          {
            delta: { content: 'Hello ' },
            finish_reason: null,
          },
        ],
      }
      yield {
        choices: [
          {
            delta: { content: 'world!' },
            finish_reason: null,
          },
        ],
      }
      yield {
        choices: [
          {
            delta: {},
            finish_reason: 'stop',
          },
        ],
      }
    })()
  }

  return Promise.resolve({
    choices: [
      {
        message: {
          content: 'Hello!',
          tool_calls: undefined,
        },
        finish_reason: 'stop',
      },
    ],
  })
})

mock.module('openai', () => ({
  default: class MockOpenAI {
    chat = {
      completions: {
        create: mockCreate,
      },
    }
  },
}))

// 动态 import 以确保 mock 生效
const { OpenAICompatProvider } = await import('../src/infra/providers/openai-compat.js')

describe('OpenAICompatProvider', () => {
  const provider = new OpenAICompatProvider()

  describe('chat', () => {
    it('应该返回 LLMResponse 格式的响应', async () => {
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
      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(result.content).toBe('Hello!')
    })

    it('finish_reason 应该是 stop', async () => {
      const result = await provider.chat({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(result.finish_reason).toBe('stop')
    })
  })

  describe('chatStream', () => {
    it('应该返回 AsyncGenerator', async () => {
      const stream = provider.chatStream({
        messages: [{ role: 'user', content: 'Hi' }],
        model: 'gpt-4o',
        baseUrl: 'https://api.openai.com/v1',
        apiKey: 'test-key',
      })

      expect(stream[Symbol.asyncIterator]).toBeDefined()
    })

    it('应该产出 text_delta 事件', async () => {
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
  })

  describe('类型结构', () => {
    it('provider 应该有 chat 和 chatStream 方法', () => {
      expect(typeof provider.chat).toBe('function')
      expect(typeof provider.chatStream).toBe('function')
    })
  })
})
