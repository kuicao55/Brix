/** 复杂度等级 */
export type Complexity = 'low' | 'medium' | 'high'

/**
 * 评估输入文本的复杂度
 * @param input - 用户输入文本
 * @returns 复杂度等级
 */
export function evaluate_complexity(input: string): Complexity {
  const wordCount = input.split(/\s+/).length
  const hasKeywords = /complex|difficult|advanced|enterprise|scale|performance|security/i.test(input)

  if (wordCount > 100 || hasKeywords) return 'high'
  if (wordCount > 30) return 'medium'
  return 'low'
}
