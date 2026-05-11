/**
 * HookRegistry — 轻量级事件注册和分发中心
 * 实现 orchestrator 层的 HookRegistry 接口
 */

import type { FlowLog } from '../log/flow.js'
import type { HookEvent } from '../types.js'

export class HookRegistry {
  private log: FlowLog | null = null
  private hooks: Map<string, Array<(event: HookEvent) => void | Promise<void>>> = new Map()

  /** 绑定 FlowLog 实例，所有事件自动转发到 log.step() */
  bindLog(log: FlowLog): void {
    this.log = log
  }

  /** 注册自定义 hook */
  register(event: string, hook: (event: HookEvent) => void | Promise<void>): void {
    const existing = this.hooks.get(event) ?? []
    existing.push(hook)
    this.hooks.set(event, existing)
  }

  /** 触发事件：先转发到 FlowLog，再调用所有注册的 hook（单个异常不影响其他） */
  async fire(name: string, data: Record<string, unknown> = {}): Promise<void> {
    // 1. 转发到 FlowLog
    if (this.log) {
      try {
        this.log.step(name, data)
      } catch (e) {
        console.warn('HookRegistry: log.step() failed:', e instanceof Error ? e.message : e)
      }
    }

    // 2. 调用注册的 hook
    const hookEvent: HookEvent = { name, data }
    const hooks = this.hooks.get(name) ?? []
    for (const hook of hooks) {
      try {
        await hook(hookEvent)
      } catch (e) {
        console.warn(`HookRegistry: hook failed for '${name}':`, e instanceof Error ? e.message : e)
      }
    }
  }
}
