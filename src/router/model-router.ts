import type { Complexity } from './complexity.js'
import type { Intent } from './intent.js'

/**
 * 根据意图和复杂度选择模型
 * @param intent - 用户意图
 * @param complexity - 复杂度等级
 * @param defaultModel - 默认模型
 * @param fallbackModel - 回退模型
 * @returns 选择的模型名
 */
export function selectModel(
  intent: Intent,
  complexity: Complexity,
  defaultModel: string,
  fallbackModel: string
): string {
  if (complexity === 'high') {
    // 高复杂度使用推理模型
    return 'claude-3-opus-20240229'
  }
  if (intent === 'task') {
    // 任务使用编码模型
    return 'claude-3-sonnet-20240229'
  }
  return defaultModel
}
