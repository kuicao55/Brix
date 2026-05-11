import type { Message, StreamEvent } from '../types.js'
import type { LLMClient } from '../infra/llm-client.js'

/**
 * 最小 HookRegistry 接口 — hooks/registry.ts 将在 milestone-12 中实现完整版本
 * 这里只定义 orchestrator 所需的最小依赖
 */
export interface HookRegistry {
  fire(name: string, data: Record<string, unknown>): Promise<void>
}

/** 工具执行器接口 — capability 层将实现完整版本 */
export interface ToolRunner {
  run(toolName: string, params: Record<string, unknown>): Promise<string>
  getToolSchemas(): Record<string, unknown>[]
}

/** Orchestrator 运行时上下文 */
export type OrchestratorContext = {
  history: Message[]
  memory: Record<string, unknown>
  toolRunner: ToolRunner | null
  llmClient: LLMClient | null
  model: string
  hooks: HookRegistry | null
}

/** Orchestrator 引擎协议 — orchestrator 层的核心接口 */
export interface OrchestratorEngine {
  run(userInput: string, context: OrchestratorContext): Promise<string>
  runStream(userInput: string, context: OrchestratorContext): AsyncGenerator<StreamEvent>
}
