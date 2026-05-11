import { describe, expect, it, mock, beforeEach } from 'bun:test'
import type { Message, LLMResponse, StreamEvent } from '../src/types.js'
import type { OrchestratorContext } from '../src/orchestrator/engine.js'

// --- 模拟 LLMClient ---
const mockChat = mock<(messages: Message[], model: string, tools?: Record<string, unknown>[]) => Promise<LLMResponse>>(
  () => Promise.resolve({ content: 'default response', tool_calls: [], finish_reason: 'stop' }),
)
const mockChatStream = mock<(messages: Message[], model: string, tools?: Record<string, unknown>[]) => AsyncGenerator<StreamEvent>>(
  async function* () {
    yield { type: 'text_delta', text: 'stream response' }
  },
)

// --- 模拟 ToolRunner ---
const mockToolRun = mock<(toolName: string, params: Record<string, unknown>) => Promise<string>>(
  () => Promise.resolve('tool result'),
)
const mockGetToolSchemas = mock<() => Record<string, unknown>[]>(
  () => [{ type: 'function', function: { name: 'test_tool', parameters: {} } }],
)

// --- 模拟 HookRegistry ---
const mockFire = mock<(name: string, data: Record<string, unknown>) => Promise<void>>(
  () => Promise.resolve(),
)

/** 默认 ToolRunner mock */
const defaultToolRunner = {
  run: mockToolRun,
  getToolSchemas: mockGetToolSchemas,
}

/** 默认 LLMClient mock */
const defaultLlmClient = {
  chat: mockChat,
  chatStream: mockChatStream,
} as any

/** 构造测试用 OrchestratorContext — 支持显式传 null 覆盖默认值 */
function makeContext(overrides?: Partial<OrchestratorContext>): OrchestratorContext {
  return {
    history: overrides?.history ?? [],
    memory: overrides?.memory ?? {},
    toolRunner: overrides && 'toolRunner' in overrides ? overrides.toolRunner! : defaultToolRunner,
    llmClient: overrides && 'llmClient' in overrides ? overrides.llmClient! : defaultLlmClient,
    model: overrides?.model ?? 'gpt-4o',
    hooks: overrides && 'hooks' in overrides ? overrides.hooks! : { fire: mockFire },
  }
}

let StateMachineOrchestrator: any

describe('StateMachineOrchestrator', () => {
  beforeEach(async () => {
    mockChat.mockClear()
    mockChatStream.mockClear()
    mockToolRun.mockClear()
    mockGetToolSchemas.mockClear()
    mockFire.mockClear()

    // 重置为默认行为
    mockChat.mockImplementation(() =>
      Promise.resolve({ content: 'default response', tool_calls: [], finish_reason: 'stop' }),
    )
    mockChatStream.mockImplementation(async function* () {
      yield { type: 'text_delta', text: 'stream response' }
    })
    mockToolRun.mockImplementation(() => Promise.resolve('tool result'))
    mockGetToolSchemas.mockImplementation(() => [
      { type: 'function', function: { name: 'test_tool', parameters: {} } },
    ])
    mockFire.mockImplementation(() => Promise.resolve())

    // 动态导入以确保 mock 生效
    const mod = await import('../src/orchestrator/state-machine.js')
    StateMachineOrchestrator = mod.StateMachineOrchestrator
  })

  describe('run() 无工具调用', () => {
    it('应该直接返回 LLM 响应内容', async () => {
      mockChat.mockImplementationOnce(() =>
        Promise.resolve({ content: 'Hello from LLM', tool_calls: [], finish_reason: 'stop' }),
      )

      const orchestrator = new StateMachineOrchestrator()
      const result = await orchestrator.run('Hi', makeContext())

      expect(result).toBe('Hello from LLM')
    })

    it('应该传递正确的 messages 给 LLM', async () => {
      mockChat.mockImplementationOnce(() =>
        Promise.resolve({ content: 'ok', tool_calls: [], finish_reason: 'stop' }),
      )

      const history: Message[] = [{ role: 'user', content: 'previous message' }]
      const orchestrator = new StateMachineOrchestrator()
      await orchestrator.run('current message', makeContext({ history }))

      const calledMessages = mockChat.mock.calls[0][0] as Message[]
      expect(calledMessages).toContainEqual({ role: 'user', content: 'previous message' })
      expect(calledMessages).toContainEqual({ role: 'user', content: 'current message' })
    })

    it('应该触发 hooks', async () => {
      mockChat.mockImplementationOnce(() =>
        Promise.resolve({ content: 'ok', tool_calls: [], finish_reason: 'stop' }),
      )

      const orchestrator = new StateMachineOrchestrator()
      await orchestrator.run('Hi', makeContext())

      // 至少触发一次 orch_plan hook
      expect(mockFire).toHaveBeenCalledWith('orch_plan', expect.objectContaining({ iteration: expect.any(Number) }))
    })
  })

  describe('run() 有工具调用', () => {
    it('应该执行工具并返回最终响应', async () => {
      // 第一次调用：返回工具调用
      // 第二次调用：返回最终文本
      let callCount = 0
      mockChat.mockImplementation(() => {
        callCount++
        if (callCount === 1) {
          return Promise.resolve({
            content: '',
            tool_calls: [{ id: 'tc_1', name: 'test_tool', arguments: { query: 'test' } }],
            finish_reason: 'tool_calls',
          })
        }
        return Promise.resolve({ content: 'Final answer', tool_calls: [], finish_reason: 'stop' })
      })

      mockToolRun.mockImplementationOnce(() => Promise.resolve('search results'))

      const orchestrator = new StateMachineOrchestrator()
      const result = await orchestrator.run('Search for something', makeContext())

      expect(result).toBe('Final answer')
      expect(mockToolRun).toHaveBeenCalledWith('test_tool', { query: 'test' })
      // 第二次 chat 调用应包含工具结果消息
      expect(mockChat).toHaveBeenCalledTimes(2)
      const secondCallMessages = mockChat.mock.calls[1][0] as Message[]
      const toolResultMsg = secondCallMessages.find(m => m.role === 'tool')
      expect(toolResultMsg).toBeDefined()
      expect(toolResultMsg!.content).toBe('search results')
      expect(toolResultMsg!.tool_call_id).toBe('tc_1')
    })

    it('应该触发 tool_exec hook 并记录工具执行', async () => {
      let callCount = 0
      mockChat.mockImplementation(() => {
        callCount++
        if (callCount === 1) {
          return Promise.resolve({
            content: '',
            tool_calls: [{ id: 'tc_1', name: 'my_tool', arguments: { x: 1 } }],
            finish_reason: 'tool_calls',
          })
        }
        return Promise.resolve({ content: 'done', tool_calls: [], finish_reason: 'stop' })
      })

      const orchestrator = new StateMachineOrchestrator()
      await orchestrator.run('do something', makeContext())

      // 检查 tool_exec hook 被触发
      const toolExecCalls = mockFire.mock.calls.filter(c => c[0] === 'tool_exec')
      expect(toolExecCalls.length).toBeGreaterThanOrEqual(1)
      expect(toolExecCalls[0][1]).toEqual(expect.objectContaining({ name: 'my_tool' }))
    })

    it('应该处理工具错误并继续', async () => {
      let callCount = 0
      mockChat.mockImplementation(() => {
        callCount++
        if (callCount === 1) {
          return Promise.resolve({
            content: '',
            tool_calls: [{ id: 'tc_1', name: 'bad_tool', arguments: {} }],
            finish_reason: 'tool_calls',
          })
        }
        return Promise.resolve({ content: 'Error handled', tool_calls: [], finish_reason: 'stop' })
      })

      mockToolRun.mockImplementationOnce(() => Promise.reject(new Error('Tool exploded')))

      const orchestrator = new StateMachineOrchestrator()
      const result = await orchestrator.run('do something', makeContext())

      // 工具错误不应中断循环，最终应返回第二次 LLM 响应
      expect(result).toBe('Error handled')
    })
  })

  describe('run() 最大迭代', () => {
    it('超过 maxIterations 后返回 Max iterations reached', async () => {
      // 始终返回工具调用以触发无限循环
      mockChat.mockImplementation(() =>
        Promise.resolve({
          content: '',
          tool_calls: [{ id: 'tc_loop', name: 'test_tool', arguments: {} }],
          finish_reason: 'tool_calls',
        }),
      )

      const orchestrator = new StateMachineOrchestrator(3)
      const result = await orchestrator.run('loop forever', makeContext())

      expect(result).toBe('Max iterations reached')
      expect(mockChat).toHaveBeenCalledTimes(3)
    })
  })

  describe('runStream() 基本功能', () => {
    it('应该 yield text_delta 事件', async () => {
      mockChatStream.mockImplementation(async function* () {
        yield { type: 'text_delta', text: 'Hello ' }
        yield { type: 'text_delta', text: 'World' }
      })

      const orchestrator = new StateMachineOrchestrator()
      const events: StreamEvent[] = []
      for await (const event of orchestrator.runStream('Hi', makeContext())) {
        events.push(event)
      }

      const textEvents = events.filter(e => e.type === 'text_delta')
      expect(textEvents).toHaveLength(2)
      expect(textEvents[0]).toEqual({ type: 'text_delta', text: 'Hello ' })
      expect(textEvents[1]).toEqual({ type: 'text_delta', text: 'World' })
    })
  })

  describe('runStream() 工具调用', () => {
    it('应该 yield tool_result 事件', async () => {
      // 第一次流：产出工具调用
      // 第二次流（无工具）：产出文本
      let streamCount = 0
      mockChatStream.mockImplementation(async function* () {
        streamCount++
        if (streamCount === 1) {
          yield { type: 'tool_call', id: 'tc_1', name: 'test_tool', input: { q: 'test' } }
        } else {
          yield { type: 'text_delta', text: 'Final' }
        }
      })

      mockToolRun.mockImplementationOnce(() => Promise.resolve('tool output'))

      const orchestrator = new StateMachineOrchestrator()
      const events: StreamEvent[] = []
      for await (const event of orchestrator.runStream('search', makeContext())) {
        events.push(event)
      }

      const toolResults = events.filter(e => e.type === 'tool_result')
      expect(toolResults).toHaveLength(1)
      expect((toolResults[0] as any).name).toBe('test_tool')
      expect((toolResults[0] as any).result).toBe('tool output')
      expect((toolResults[0] as any).is_error).toBe(false)
      expect((toolResults[0] as any).ms).toBeGreaterThanOrEqual(0)

      const textEvents = events.filter(e => e.type === 'text_delta')
      expect(textEvents).toHaveLength(1)
    })

    it('工具错误时应该 yield is_error: true 的 tool_result', async () => {
      let streamCallCount = 0
      mockChatStream.mockImplementation(async function* () {
        streamCallCount++
        if (streamCallCount === 1) {
          yield { type: 'tool_call', id: 'tc_err', name: 'bad_tool', input: {} }
        }
        // 第二次调用不产出任何事件 → 无工具调用 → 退出循环
      })

      mockToolRun.mockImplementationOnce(() => Promise.reject(new Error('boom')))

      const orchestrator = new StateMachineOrchestrator()
      const events: StreamEvent[] = []
      for await (const event of orchestrator.runStream('fail', makeContext())) {
        events.push(event)
      }

      const toolResults = events.filter(e => e.type === 'tool_result')
      expect(toolResults).toHaveLength(1)
      expect((toolResults[0] as any).is_error).toBe(true)
    })
  })

  describe('null 安全', () => {
    it('llmClient 为 null 时 run() 应抛出错误', async () => {
      const orchestrator = new StateMachineOrchestrator()
      await expect(
        orchestrator.run('Hi', makeContext({ llmClient: null })),
      ).rejects.toThrow()
    })

    it('toolRunner 为 null 且需要工具时 run() 应处理', async () => {
      mockChat.mockImplementationOnce(() =>
        Promise.resolve({
          content: '',
          tool_calls: [{ id: 'tc_1', name: 'test_tool', arguments: {} }],
          finish_reason: 'tool_calls',
        }),
      )

      const orchestrator = new StateMachineOrchestrator()
      // toolRunner 为 null 时应抛出错误而不是 crash
      await expect(
        orchestrator.run('Hi', makeContext({ toolRunner: null })),
      ).rejects.toThrow()
    })

    it('hooks 为 null 时不应崩溃', async () => {
      mockChat.mockImplementationOnce(() =>
        Promise.resolve({ content: 'ok', tool_calls: [], finish_reason: 'stop' }),
      )

      const orchestrator = new StateMachineOrchestrator()
      const result = await orchestrator.run('Hi', makeContext({ hooks: null }))
      expect(result).toBe('ok')
    })
  })

  describe('默认 maxIterations', () => {
    it('默认值应为 100', async () => {
      // 验证构造函数默认参数
      // 如果默认不是 100，此测试会在后续 run 中体现
      mockChat.mockImplementation(() =>
        Promise.resolve({ content: '', tool_calls: [{ id: 'tc', name: 'test_tool', arguments: {} }], finish_reason: 'tool_calls' }),
      )
      mockToolRun.mockImplementation(() => Promise.resolve('r'))

      const orchestrator = new StateMachineOrchestrator()
      const result = await orchestrator.run('test', makeContext())

      // 如果默认 maxIterations 是 100，应该调用 100 次 chat
      expect(mockChat).toHaveBeenCalledTimes(100)
      expect(result).toBe('Max iterations reached')
    })
  })
})
