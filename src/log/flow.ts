/**
 * FlowLog — 内存中的步骤收集器
 * 记录一次对话轮次中的所有管道步骤，最终序列化为 JSONL
 */

export class FlowLog {
  private traceId: string
  private startTime: number
  private steps: Array<{ module: string; data: Record<string, unknown>; ts: number }> = []
  private model: string = ''
  private error: string | null = null
  private input: string

  constructor(input: string) {
    this.input = input
    this.traceId = crypto.randomUUID().replace(/-/g, '').slice(0, 8)
    this.startTime = performance.now()
  }

  /** 记录一个管道步骤 */
  step(module: string, data: Record<string, unknown> = {}): void {
    if (!module) return
    this.steps.push({ module, data, ts: performance.now() })
  }

  /** 设置当前使用的模型 */
  setModel(model: string): void {
    this.model = model
  }

  /** 设置错误信息 */
  setError(error: string): void {
    this.error = error
  }

  /** 获取 trace ID */
  getTraceId(): string {
    return this.traceId
  }

  /** 序列化为 JSONL-ready 对象 */
  finish(): Record<string, unknown> {
    const msTotal = Math.round(performance.now() - this.startTime)
    const llmCalls = this.steps.filter(s => 'ms' in s.data && s.module !== 'tool_exec').length
    const tools = this.steps.filter(s => s.module === 'tool_exec').length
    const iters = this.steps.filter(s => s.module === 'orch_plan').length

    return {
      ts: new Date().toISOString().replace(/\.\d{3}Z$/, ''),
      trace: this.traceId,
      input: this.input,
      steps: this.steps.map(s => ({
        m: s.module,
        at: new Date(s.ts).toISOString().split('T')[1]?.replace('Z', '') ?? '',
        ...s.data,
      })),
      model: this.model,
      iters,
      tools,
      llm_calls: llmCalls,
      ms_total: msTotal,
      error: this.error,
    }
  }
}
