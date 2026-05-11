import type { LLMClient } from '../infra/llm-client.js'

/** 意图分类类型 */
export type Intent = 'chat' | 'task' | 'tool_use'

/**
 * 最小 HookRegistry 接口 — hooks/registry.ts 将在 milestone-12 中实现完整版本
 * 这里只定义 classifyIntent 所需的最小依赖
 */
export interface IntentHookRegistry {
  fire(name: string, data: Record<string, unknown>): Promise<void>
}

const KEYWORDS_TASK = ['create', 'build', 'make', 'implement', 'fix', 'refactor', 'update', 'change', 'add', 'remove', 'delete']
const KEYWORDS_TOOL = ['calculate', 'weather', 'file', 'read', 'write', 'edit']

/**
 * 意图分类 — 通过 LLM 分类，失败时回退到关键词启发式
 * @param input - 用户输入文本
 * @param llmClient - LLM 客户端
 * @param model - 模型名
 * @param hooks - 可选的 hook 注册表（milestone-12 实现）
 */
export async function classifyIntent(
  input: string,
  llmClient: LLMClient,
  model: string,
  hooks?: IntentHookRegistry
): Promise<Intent> {
  // 触发 hook — fire-and-forget，hook 不阻塞分类（失败/慢都不影响主流程）
  if (hooks) {
    hooks.fire('intent', { input }).catch(() => {})
  }

  try {
    // 尝试 LLM 分类
    const response = await llmClient.chat(
      [{ role: 'user', content: `Classify the following user input as "chat", "task", or "tool_use": "${input}"` }],
      model
    )
    const intent = response.content.trim().toLowerCase()
    if (intent === 'chat' || intent === 'task' || intent === 'tool_use') {
      return intent
    }
  } catch {
    // LLM 失败，回退到关键词启发式
  }

  // 关键词启发式
  const lowerInput = input.toLowerCase()
  if (KEYWORDS_TASK.some(kw => lowerInput.includes(kw))) return 'task'
  if (KEYWORDS_TOOL.some(kw => lowerInput.includes(kw))) return 'tool_use'
  return 'chat'
}
