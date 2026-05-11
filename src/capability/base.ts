/**
 * 工具接口 — capability 层的核心协议
 * 所有工具必须实现此接口
 */
export interface Tool {
  readonly name: string
  readonly description: string
  readonly inputSchema: Record<string, unknown>
  execute(params: Record<string, unknown>): Promise<string>
  toOpenAiSchema(): Record<string, unknown>
}

/**
 * 工具基类 — 提供 toOpenAiSchema() 默认实现
 * 子类只需实现 name, description, inputSchema, execute
 */
export abstract class BaseTool implements Tool {
  abstract readonly name: string
  abstract readonly description: string
  abstract readonly inputSchema: Record<string, unknown>
  abstract execute(params: Record<string, unknown>): Promise<string>

  toOpenAiSchema(): Record<string, unknown> {
    return {
      type: 'function',
      function: {
        name: this.name,
        description: this.description,
        parameters: this.inputSchema,
      },
    }
  }
}
