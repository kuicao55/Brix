import { describe, expect, it, mock, beforeEach } from 'bun:test'
import type { Message, LLMResponse, StreamEvent } from '../src/types.js'

// Mock 两个 provider — 不调用真实 API
const mockOpenAIChat = mock<(params: Record<string, unknown>) => Promise<LLMResponse>>(() =>
  Promise.resolve({ content: 'openai response', tool_calls: [], finish_reason: 'stop' })
)
const mockOpenAIStream = mock<(params: Record<string, unknown>) => AsyncGenerator<StreamEvent>>(
  async function* () {
    yield { type: 'text_delta', text: 'openai stream' }
  }
)
const mockAnthropicChat = mock<(params: Record<string, unknown>) => Promise<LLMResponse>>(() =>
  Promise.resolve({ content: 'anthropic response', tool_calls: [], finish_reason: 'end_turn' })
)
const mockAnthropicStream = mock<(params: Record<string, unknown>) => AsyncGenerator<StreamEvent>>(
  async function* () {
    yield { type: 'text_delta', text: 'anthropic stream' }
  }
)

mock.module('../src/infra/providers/openai-compat.js', () => ({
  OpenAICompatProvider: class {
    chat = mockOpenAIChat
    chatStream = mockOpenAIStream
  },
}))

mock.module('../src/infra/providers/anthropic-compat.js', () => ({
  AnthropicCompatProvider: class {
    chat = mockAnthropicChat
    chatStream = mockAnthropicStream
  },
}))

const { LLMClient } = await import('../src/infra/llm-client.js')

/** 构造测试用 BrixConfig */
function makeConfig(overrides?: Partial<{
  providers: Record<string, { base_url: string; api_key_env: string; protocol: 'openai' | 'anthropic' }>
  retry: { max_retries: number; base_delay: number; max_delay: number }
  routing: { default_model: string; fallback_model: string }
}>) {
  return {
    providers: overrides?.providers ?? {
      openai: { base_url: 'https://api.openai.com/v1', api_key_env: 'OPENAI_API_KEY', protocol: 'openai' as const },
    },
    models: [],
    engine: 'state_machine',
    routing: overrides?.routing ?? { default_model: 'gpt-4o', fallback_model: 'gpt-4o-mini' },
    retry: overrides?.retry ?? { max_retries: 2, base_delay: 0.01, max_delay: 0.05 },
    memory: { data_dir: 'test/data', max_context_tokens: 8000 },
  }
}

describe('LLMClient', () => {
  beforeEach(() => {
    mockOpenAIChat.mockClear()
    mockOpenAIStream.mockClear()
    mockAnthropicChat.mockClear()
    mockAnthropicStream.mockClear()
  })

  describe('构造函数', () => {
    it('应该接受 BrixConfig 并创建实例', () => {
      const client = new LLMClient(makeConfig())
      expect(client).toBeDefined()
    })
  })

  describe('chat', () => {
    it('应该委托给 OpenAI provider 并返回 LLMResponse', async () => {
      const client = new LLMClient(makeConfig())

      const result = await client.chat(
        [{ role: 'user', content: 'Hi' }],
        'gpt-4o',
      )

      expect(result.content).toBe('openai response')
      expect(result.finish_reason).toBe('stop')
      expect(mockOpenAIChat).toHaveBeenCalledTimes(1)
    })

    it('应该委托给 Anthropic provider', async () => {
      const client = new LLMClient(makeConfig({
        providers: {
          anthropic: { base_url: 'https://api.anthropic.com', api_key_env: 'ANTHROPIC_API_KEY', protocol: 'anthropic' },
        },
      }))

      const result = await client.chat(
        [{ role: 'user', content: 'Hi' }],
        'claude-sonnet-4-20250514',
      )

      expect(result.content).toBe('anthropic response')
      expect(result.finish_reason).toBe('end_turn')
      expect(mockAnthropicChat).toHaveBeenCalledTimes(1)
    })

    it('应该传递 messages、model、tools 参数给 provider', async () => {
      const client = new LLMClient(makeConfig())
      const messages: Message[] = [{ role: 'user', content: 'test' }]
      const tools = [{ type: 'function', function: { name: 'test_tool', parameters: {} } }]

      await client.chat(messages, 'gpt-4o', tools)

      const calledParams = mockOpenAIChat.mock.calls[0][0] as Record<string, unknown>
      expect(calledParams.messages).toEqual(messages)
      expect(calledParams.model).toBe('gpt-4o')
      expect(calledParams.tools).toEqual(tools)
    })

    it('无 provider 配置时应该抛出错误', async () => {
      const client = new LLMClient(makeConfig({ providers: {} }))

      await expect(
        client.chat([{ role: 'user', content: 'Hi' }], 'gpt-4o')
      ).rejects.toThrow()
    })
  })

  describe('chatStream', () => {
    it('应该委托给 OpenAI provider 并返回 AsyncGenerator', async () => {
      const client = new LLMClient(makeConfig())

      const stream = client.chatStream(
        [{ role: 'user', content: 'Hi' }],
        'gpt-4o',
      )

      expect(stream[Symbol.asyncIterator]).toBeDefined()

      const events: StreamEvent[] = []
      for await (const event of stream) {
        events.push(event)
      }
      expect(events).toHaveLength(1)
      expect(events[0]).toEqual({ type: 'text_delta', text: 'openai stream' })
    })

    it('应该委托给 Anthropic provider', async () => {
      const client = new LLMClient(makeConfig({
        providers: {
          anthropic: { base_url: 'https://api.anthropic.com', api_key_env: 'ANTHROPIC_API_KEY', protocol: 'anthropic' },
        },
      }))

      const stream = client.chatStream(
        [{ role: 'user', content: 'Hi' }],
        'claude-sonnet-4-20250514',
      )

      const events: StreamEvent[] = []
      for await (const event of stream) {
        events.push(event)
      }
      expect(events).toHaveLength(1)
      expect(events[0]).toEqual({ type: 'text_delta', text: 'anthropic stream' })
    })
  })

  describe('retry', () => {
    it('在 retryable 错误后应该重试', async () => {
      let callCount = 0
      mockOpenAIChat.mockImplementation(() => {
        callCount++
        if (callCount === 1) {
          const err = new Error('Rate limit exceeded')
          err.name = 'RateLimitError'
          return Promise.reject(err)
        }
        return Promise.resolve({ content: 'success after retry', tool_calls: [], finish_reason: 'stop' })
      })

      const client = new LLMClient(makeConfig({
        retry: { max_retries: 2, base_delay: 0.01, max_delay: 0.05 },
      }))

      const result = await client.chat(
        [{ role: 'user', content: 'Hi' }],
        'gpt-4o',
      )

      expect(result.content).toBe('success after retry')
      expect(callCount).toBe(2)
    })

    it('超过最大重试次数后应该抛出错误', async () => {
      mockOpenAIChat.mockImplementation(() => {
        const err = new Error('Rate limit exceeded')
        err.name = 'RateLimitError'
        return Promise.reject(err)
      })

      const client = new LLMClient(makeConfig({
        retry: { max_retries: 1, base_delay: 0.01, max_delay: 0.05 },
      }))

      await expect(
        client.chat([{ role: 'user', content: 'Hi' }], 'gpt-4o')
      ).rejects.toThrow('Rate limit exceeded')
    })

    it('非 retryable 错误应该直接抛出', async () => {
      mockOpenAIChat.mockImplementation(() => {
        return Promise.reject(new Error('Invalid request'))
      })

      const client = new LLMClient(makeConfig({
        retry: { max_retries: 3, base_delay: 0.01, max_delay: 0.05 },
      }))

      await expect(
        client.chat([{ role: 'user', content: 'Hi' }], 'gpt-4o')
      ).rejects.toThrow('Invalid request')
      // 非 retryable 错误不重试，只调用一次
      expect(mockOpenAIChat).toHaveBeenCalledTimes(1)
    })

    it('5xx 状态码错误应该重试', async () => {
      let callCount = 0
      mockOpenAIChat.mockImplementation(() => {
        callCount++
        if (callCount === 1) {
          const err = new Error('Internal Server Error') as Error & { status: number }
          err.name = 'Error'
          err.status = 500
          return Promise.reject(err)
        }
        return Promise.resolve({ content: 'success after 5xx', tool_calls: [], finish_reason: 'stop' })
      })

      const client = new LLMClient(makeConfig({
        retry: { max_retries: 2, base_delay: 0.01, max_delay: 0.05 },
      }))

      const result = await client.chat(
        [{ role: 'user', content: 'Hi' }],
        'gpt-4o',
      )

      expect(result.content).toBe('success after 5xx')
      expect(callCount).toBe(2)
    })
  })

  describe('API key 传递', () => {
    it('应该从环境变量读取 API key 并传递给 provider', async () => {
      process.env.TEST_API_KEY = 'test-secret-key'
      const client = new LLMClient(makeConfig({
        providers: {
          openai: { base_url: 'https://api.test.com/v1', api_key_env: 'TEST_API_KEY', protocol: 'openai' },
        },
      }))

      await client.chat([{ role: 'user', content: 'Hi' }], 'gpt-4o')

      const calledParams = mockOpenAIChat.mock.calls[0][0] as Record<string, unknown>
      expect(calledParams.apiKey).toBe('test-secret-key')
      expect(calledParams.baseUrl).toBe('https://api.test.com/v1')

      delete process.env.TEST_API_KEY
    })

    it('环境变量不存在时应该传递空字符串', async () => {
      delete process.env.NONEXISTENT_KEY
      const client = new LLMClient(makeConfig({
        providers: {
          openai: { base_url: 'https://api.test.com/v1', api_key_env: 'NONEXISTENT_KEY', protocol: 'openai' },
        },
      }))

      await client.chat([{ role: 'user', content: 'Hi' }], 'gpt-4o')

      const calledParams = mockOpenAIChat.mock.calls[0][0] as Record<string, unknown>
      expect(calledParams.apiKey).toBe('')
    })
  })

  describe('未知协议', () => {
    it('应该在遇到未知 protocol 时抛出错误', async () => {
      const client = new LLMClient(makeConfig({
        providers: {
          weird: { base_url: 'https://api.weird.com', api_key_env: 'KEY', protocol: 'weird' as 'openai' },
        },
      }))

      await expect(
        client.chat([{ role: 'user', content: 'Hi' }], 'weird-model')
      ).rejects.toThrow()
    })
  })
})
