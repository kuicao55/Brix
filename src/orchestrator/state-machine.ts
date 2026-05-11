import type { Message, StreamEvent } from '../types.js'
import type { OrchestratorEngine, OrchestratorContext } from './engine.js'

/**
 * 状态机编排器 — 实现 OrchestratorEngine 协议
 * 同步循环：plan → call LLM → (tool_exec → feed back)* → respond
 */
export class StateMachineOrchestrator implements OrchestratorEngine {
  private maxIterations: number

  constructor(maxIterations: number = 100) {
    this.maxIterations = maxIterations
  }

  /**
   * 非流式运行：循环调用 LLM 直到无工具调用或达到最大迭代
   */
  async run(userInput: string, context: OrchestratorContext): Promise<string> {
    const { llmClient, toolRunner, hooks, model, history } = context

    // null 安全检查
    if (!llmClient) {
      throw new Error('llmClient is required')
    }

    // 构建消息列表：历史 + 用户输入
    const messages: Message[] = [...history, { role: 'user', content: userInput }]

    for (let iteration = 0; iteration < this.maxIterations; iteration++) {
      // 触发 plan hook — best-effort，hook 失败不阻塞编排
      try {
        await hooks?.fire('orch_plan', { iteration })
      } catch (e) {
        console.warn('hook fire failed:', e instanceof Error ? e.message : e)
      }

      // 调用 LLM
      const tools = toolRunner?.getToolSchemas()
      const response = await llmClient.chat(messages, model, tools)

      // 无工具调用 → 返回最终响应
      if (!response.tool_calls || response.tool_calls.length === 0) {
        return response.content
      }

      // 记录 assistant 消息（含工具调用）
      messages.push({
        role: 'assistant',
        content: response.content,
        tool_calls: response.tool_calls,
      })

      // 执行每个工具调用
      for (const toolCall of response.tool_calls) {
        if (!toolRunner) {
          throw new Error('toolRunner is required to execute tool calls')
        }

        // 触发 tool_exec hook — best-effort，hook 失败不阻塞工具执行
        try {
          await hooks?.fire('tool_exec', { name: toolCall.name, id: toolCall.id })
        } catch (e) {
          console.warn('hook fire failed:', e instanceof Error ? e.message : e)
        }

        let result: string
        try {
          result = await toolRunner.run(toolCall.name, toolCall.arguments)
        } catch (err) {
          // 工具执行失败时将错误信息作为结果返回给 LLM
          result = `Error: ${err instanceof Error ? err.message : String(err)}`
        }

        // 推送工具结果消息
        messages.push({
          role: 'tool',
          content: result,
          tool_call_id: toolCall.id,
          tool_name: toolCall.name,
        })
      }
    }

    return 'Max iterations reached'
  }

  /**
   * 流式运行：使用 chatStream 产出 StreamEvent
   */
  async *runStream(userInput: string, context: OrchestratorContext): AsyncGenerator<StreamEvent> {
    const { llmClient, toolRunner, hooks, model, history } = context

    // null 安全检查
    if (!llmClient) {
      throw new Error('llmClient is required')
    }

    const messages: Message[] = [...history, { role: 'user', content: userInput }]

    for (let iteration = 0; iteration < this.maxIterations; iteration++) {
      // 触发 plan hook — best-effort，hook 失败不阻塞编排
      try {
        await hooks?.fire('orch_plan', { iteration })
      } catch (e) {
        console.warn('hook fire failed:', e instanceof Error ? e.message : e)
      }

      const tools = toolRunner?.getToolSchemas()

      // 收集本轮流式事件
      const collectedToolCalls: Array<{ id: string; name: string; input: Record<string, unknown> }> = []
      let assistantContent = ''

      for await (const event of llmClient.chatStream(messages, model, tools)) {
        if (event.type === 'text_delta') {
          assistantContent += event.text
          yield event
        } else if (event.type === 'tool_call') {
          collectedToolCalls.push(event)
          yield event
        }
      }

      // 无工具调用 → 结束
      if (collectedToolCalls.length === 0) {
        return
      }

      // 记录 assistant 消息
      messages.push({
        role: 'assistant',
        content: assistantContent,
        tool_calls: collectedToolCalls.map(tc => ({
          id: tc.id,
          name: tc.name,
          arguments: tc.input,
        })),
      })

      // 执行工具并产出结果
      for (const toolCall of collectedToolCalls) {
        if (!toolRunner) {
          throw new Error('toolRunner is required to execute tool calls')
        }

        // 触发 tool_exec hook — best-effort，hook 失败不阻塞工具执行
        try {
          await hooks?.fire('tool_exec', { name: toolCall.name, id: toolCall.id })
        } catch (e) {
          console.warn('hook fire failed:', e instanceof Error ? e.message : e)
        }

        const startTime = Date.now()
        let result: string
        let isError = false

        try {
          result = await toolRunner.run(toolCall.name, toolCall.input)
        } catch (err) {
          result = `Error: ${err instanceof Error ? err.message : String(err)}`
          isError = true
        }

        const ms = Date.now() - startTime

        // 产出工具结果事件
        yield {
          type: 'tool_result',
          id: toolCall.id,
          name: toolCall.name,
          result,
          ms,
          is_error: isError,
        }

        // 推送工具结果消息
        messages.push({
          role: 'tool',
          content: result,
          tool_call_id: toolCall.id,
          tool_name: toolCall.name,
        })
      }
    }
  }
}
