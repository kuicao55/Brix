import type { Tool } from './base.js'
import type { ToolRunner as ToolRunnerProtocol } from '../orchestrator/engine.js'

/**
 * 工具执行器 — 管理和执行已注册的工具
 * 实现 orchestrator 层的 ToolRunnerProtocol 接口
 */
export class ToolRunner implements ToolRunnerProtocol {
  private tools: Map<string, Tool> = new Map()

  /** 注册工具（同名覆盖） */
  register(tool: Tool): void {
    this.tools.set(tool.name, tool)
  }

  /** 执行指定工具 */
  async run(toolName: string, params: Record<string, unknown>): Promise<string> {
    const tool = this.tools.get(toolName)
    if (!tool) throw new Error(`Unknown tool: ${toolName}`)
    return await tool.execute(params)
  }

  /** 获取所有已注册工具的 OpenAI schema */
  getToolSchemas(): Record<string, unknown>[] {
    return [...this.tools.values()].map(t => t.toOpenAiSchema())
  }
}
