import { describe, expect, it, mock, beforeEach } from 'bun:test'
import type { LLMResponse } from '../src/types.js'

// Mock LLMClient — 不调用真实 API
const mockChat = mock<(messages: { role: string; content: string }[], model: string) => Promise<LLMResponse>>(() =>
  Promise.resolve({ content: 'chat', tool_calls: [], finish_reason: 'stop' })
)

const mockLLMClient = { chat: mockChat } as unknown as import('../src/infra/llm-client.js').LLMClient

const { classifyIntent } = await import('../src/router/intent.js')

describe('classifyIntent', () => {
  beforeEach(() => {
    mockChat.mockClear()
    // 默认实现：返回 'chat'
    mockChat.mockImplementation(() =>
      Promise.resolve({ content: 'chat', tool_calls: [], finish_reason: 'stop' })
    )
  })

  describe('LLM 分类成功', () => {
    it('LLM 返回 "chat" 时应返回 chat', async () => {
      mockChat.mockResolvedValueOnce({ content: 'chat', tool_calls: [], finish_reason: 'stop' })

      const result = await classifyIntent('Hello, how are you?', mockLLMClient, 'gpt-4o')
      expect(result).toBe('chat')
    })

    it('LLM 返回 "task" 时应返回 task', async () => {
      mockChat.mockResolvedValueOnce({ content: 'task', tool_calls: [], finish_reason: 'stop' })

      const result = await classifyIntent('Build a login page', mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })

    it('LLM 返回 "tool_use" 时应返回 tool_use', async () => {
      mockChat.mockResolvedValueOnce({ content: 'tool_use', tool_calls: [], finish_reason: 'stop' })

      const result = await classifyIntent('Calculate 2+2', mockLLMClient, 'gpt-4o')
      expect(result).toBe('tool_use')
    })

    it('LLM 返回带空格的意图应 trim 后匹配', async () => {
      mockChat.mockResolvedValueOnce({ content: '  TASK  ', tool_calls: [], finish_reason: 'stop' })

      const result = await classifyIntent('Some input', mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })
  })

  describe('LLM 返回无效值时回退到关键词启发式', () => {
    it('LLM 返回无效字符串应使用关键词回退', async () => {
      mockChat.mockResolvedValueOnce({ content: 'invalid_intent', tool_calls: [], finish_reason: 'stop' })

      // "create" 在 KEYWORDS_TASK 中
      const result = await classifyIntent('Create a new component', mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })

    it('LLM 返回空字符串应使用关键词回退', async () => {
      mockChat.mockResolvedValueOnce({ content: '', tool_calls: [], finish_reason: 'stop' })

      // "calculate" 在 KEYWORDS_TOOL 中
      const result = await classifyIntent('Calculate the sum', mockLLMClient, 'gpt-4o')
      expect(result).toBe('tool_use')
    })
  })

  describe('LLM 调用失败时回退到关键词启发式', () => {
    it('LLM 抛出错误时应使用关键词回退到 task', async () => {
      mockChat.mockRejectedValueOnce(new Error('API error'))

      const result = await classifyIntent('Fix the bug in auth module', mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })

    it('LLM 抛出错误时应使用关键词回退到 tool_use', async () => {
      mockChat.mockRejectedValueOnce(new Error('API error'))

      const result = await classifyIntent('Read the file config.json', mockLLMClient, 'gpt-4o')
      expect(result).toBe('tool_use')
    })

    it('LLM 抛出错误且无关键词匹配时应返回 chat', async () => {
      mockChat.mockRejectedValueOnce(new Error('API error'))

      const result = await classifyIntent('Hello there!', mockLLMClient, 'gpt-4o')
      expect(result).toBe('chat')
    })
  })

  describe('关键词启发式', () => {
    const taskKeywords = ['create', 'build', 'make', 'implement', 'fix', 'refactor', 'update', 'change', 'add', 'remove', 'delete']
    const toolKeywords = ['calculate', 'weather', 'file', 'read', 'write', 'edit']

    it.each(taskKeywords)('关键词 "%s" 应分类为 task', async (keyword) => {
      mockChat.mockRejectedValueOnce(new Error('fallback'))

      const result = await classifyIntent(`Please ${keyword} something`, mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })

    it.each(toolKeywords)('关键词 "%s" 应分类为 tool_use', async (keyword) => {
      mockChat.mockRejectedValueOnce(new Error('fallback'))

      const result = await classifyIntent(`Please ${keyword} something`, mockLLMClient, 'gpt-4o')
      expect(result).toBe('tool_use')
    })
  })

  describe('优先级', () => {
    it('task 关键词优先于 tool_use 关键词', async () => {
      mockChat.mockRejectedValueOnce(new Error('fallback'))

      // "create" 是 task 关键词, "file" 是 tool 关键词
      const result = await classifyIntent('Create a file', mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })
  })

  describe('大小写不敏感', () => {
    it('关键词匹配应不区分大小写', async () => {
      mockChat.mockRejectedValueOnce(new Error('fallback'))

      const result = await classifyIntent('FIX the Bug', mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })

    it('LLM 返回应不区分大小写', async () => {
      mockChat.mockResolvedValueOnce({ content: 'Task', tool_calls: [], finish_reason: 'stop' })

      const result = await classifyIntent('Build a page', mockLLMClient, 'gpt-4o')
      expect(result).toBe('task')
    })
  })

  describe('hooks 集成', () => {
    it('应触发 hooks.fire 并传入 intent 事件和 input', async () => {
      const mockFire = mock<(name: string, data: Record<string, unknown>) => Promise<void>>(() =>
        Promise.resolve()
      )
      const hooks = { fire: mockFire } as unknown as NonNullable<Parameters<typeof classifyIntent>[3]>

      await classifyIntent('Hello', mockLLMClient, 'gpt-4o', hooks)

      expect(mockFire).toHaveBeenCalledTimes(1)
      expect(mockFire).toHaveBeenCalledWith('intent', { input: 'Hello' })
    })

    it('无 hooks 时不应抛出错误', async () => {
      await expect(classifyIntent('Hello', mockLLMClient, 'gpt-4o')).resolves.toBeDefined()
    })

    it('有 hooks 时仍应返回正确的意图', async () => {
      const mockFire = mock(() => Promise.resolve())
      const hooks = { fire: mockFire } as unknown as NonNullable<Parameters<typeof classifyIntent>[3]>
      mockChat.mockResolvedValueOnce({ content: 'task', tool_calls: [], finish_reason: 'stop' })

      const result = await classifyIntent('Build a page', mockLLMClient, 'gpt-4o', hooks)
      expect(result).toBe('task')
    })

    it('hooks.fire 抛出错误时不应阻塞意图分类', async () => {
      const mockFire = mock(() => Promise.reject(new Error('telemetry network failure')))
      const hooks = { fire: mockFire } as unknown as NonNullable<Parameters<typeof classifyIntent>[3]>
      mockChat.mockResolvedValueOnce({ content: 'task', tool_calls: [], finish_reason: 'stop' })

      const result = await classifyIntent('Build a page', mockLLMClient, 'gpt-4o', hooks)
      expect(result).toBe('task')
    })

    it('hooks.fire 抛出错误且 LLM 也失败时应通过关键词回退分类', async () => {
      const mockFire = mock(() => Promise.reject(new Error('hook crash')))
      const hooks = { fire: mockFire } as unknown as NonNullable<Parameters<typeof classifyIntent>[3]>
      mockChat.mockRejectedValueOnce(new Error('API error'))

      const result = await classifyIntent('Fix the bug', mockLLMClient, 'gpt-4o', hooks)
      expect(result).toBe('task')
    })
  })
})

// ============================================================
// evaluateComplexity 测试
// ============================================================
const { evaluate_complexity } = await import('../src/router/complexity.js')

describe('evaluateComplexity', () => {
  describe('低复杂度', () => {
    it('短输入（<=30 词）应返回 low', () => {
      expect(evaluate_complexity('Hello, how are you?')).toBe('low')
    })

    it('单个单词应返回 low', () => {
      expect(evaluate_complexity('hello')).toBe('low')
    })

    it('空字符串应返回 low', () => {
      expect(evaluate_complexity('')).toBe('low')
    })

    it('恰好 30 词应返回 low', () => {
      const input = Array(30).fill('word').join(' ')
      expect(evaluate_complexity(input)).toBe('low')
    })
  })

  describe('中等复杂度', () => {
    it('31-100 词且无关键词应返回 medium', () => {
      const input = Array(50).fill('word').join(' ')
      expect(evaluate_complexity(input)).toBe('medium')
    })

    it('恰好 31 词应返回 medium', () => {
      const input = Array(31).fill('word').join(' ')
      expect(evaluate_complexity(input)).toBe('medium')
    })

    it('恰好 100 词且无关键词应返回 medium', () => {
      const input = Array(100).fill('word').join(' ')
      expect(evaluate_complexity(input)).toBe('medium')
    })
  })

  describe('高复杂度', () => {
    it('超过 100 词应返回 high', () => {
      const input = Array(101).fill('word').join(' ')
      expect(evaluate_complexity(input)).toBe('high')
    })

    it('包含 "complex" 关键词应返回 high', () => {
      expect(evaluate_complexity('This is a complex problem')).toBe('high')
    })

    it('包含 "difficult" 关键词应返回 high', () => {
      expect(evaluate_complexity('This is a difficult task')).toBe('high')
    })

    it('包含 "advanced" 关键词应返回 high', () => {
      expect(evaluate_complexity('advanced configuration')).toBe('high')
    })

    it('包含 "enterprise" 关键词应返回 high', () => {
      expect(evaluate_complexity('enterprise solution')).toBe('high')
    })

    it('包含 "scale" 关键词应返回 high', () => {
      expect(evaluate_complexity('scale the application')).toBe('high')
    })

    it('包含 "performance" 关键词应返回 high', () => {
      expect(evaluate_complexity('performance optimization')).toBe('high')
    })

    it('包含 "security" 关键词应返回 high', () => {
      expect(evaluate_complexity('security audit')).toBe('high')
    })

    it('关键词匹配应不区分大小写', () => {
      expect(evaluate_complexity('COMPLEX')).toBe('high')
      expect(evaluate_complexity('Performance')).toBe('high')
    })

    it('短输入但有关键词应返回 high', () => {
      expect(evaluate_complexity('complex')).toBe('high')
    })
  })
})

// ============================================================
// selectModel 测试
// ============================================================
const { selectModel } = await import('../src/router/model-router.js')

describe('selectModel', () => {
  const defaultModel = 'gpt-4o-mini'
  const fallbackModel = 'gpt-3.5-turbo'

  describe('高复杂度路由', () => {
    it('high 复杂度应返回 opus 模型，忽略 intent', () => {
      expect(selectModel('chat', 'high', defaultModel, fallbackModel)).toBe('claude-3-opus-20240229')
      expect(selectModel('task', 'high', defaultModel, fallbackModel)).toBe('claude-3-opus-20240229')
      expect(selectModel('tool_use', 'high', defaultModel, fallbackModel)).toBe('claude-3-opus-20240229')
    })
  })

  describe('任务路由', () => {
    it('task 意图且非 high 复杂度应返回 sonnet 模型', () => {
      expect(selectModel('task', 'low', defaultModel, fallbackModel)).toBe('claude-3-sonnet-20240229')
      expect(selectModel('task', 'medium', defaultModel, fallbackModel)).toBe('claude-3-sonnet-20240229')
    })
  })

  describe('默认路由', () => {
    it('chat 意图且 low 复杂度应返回 defaultModel', () => {
      expect(selectModel('chat', 'low', defaultModel, fallbackModel)).toBe(defaultModel)
    })

    it('chat 意图且 medium 复杂度应返回 defaultModel', () => {
      expect(selectModel('chat', 'medium', defaultModel, fallbackModel)).toBe(defaultModel)
    })

    it('tool_use 意图且 low 复杂度应返回 defaultModel', () => {
      expect(selectModel('tool_use', 'low', defaultModel, fallbackModel)).toBe(defaultModel)
    })

    it('tool_use 意图且 medium 复杂度应返回 defaultModel', () => {
      expect(selectModel('tool_use', 'medium', defaultModel, fallbackModel)).toBe(defaultModel)
    })

    it('应返回传入的 defaultModel 参数', () => {
      const custom = 'my-custom-model'
      expect(selectModel('chat', 'low', custom, fallbackModel)).toBe(custom)
    })
  })
})
