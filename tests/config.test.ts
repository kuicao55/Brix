import { describe, expect, it } from 'bun:test'
import { ModelRegistry } from '../src/config/model-registry.js'
import type { ModelConfig } from '../src/config/loader.js'

const makeModel = (overrides: Partial<ModelConfig> = {}): ModelConfig => ({
  id: 'test-model',
  provider: 'openai',
  purpose: ['coding', 'chat'],
  capabilities: ['text'],
  max_context: 128000,
  cost_tier: 'medium',
  ...overrides,
})

describe('ModelRegistry', () => {
  const models: ModelConfig[] = [
    makeModel({ id: 'gpt-4o', purpose: ['coding', 'chat'], provider: 'openai' }),
    makeModel({ id: 'claude-3-sonnet', purpose: ['coding', 'analysis'], provider: 'anthropic' }),
    makeModel({ id: 'gpt-4o-mini', purpose: ['chat'], provider: 'openai' }),
  ]

  it('应该通过 id 查找模型', () => {
    const registry = new ModelRegistry(models, 'gpt-4o', 'gpt-4o-mini')
    expect(registry.getModelById('gpt-4o')).toBeDefined()
    expect(registry.getModelById('gpt-4o')?.provider).toBe('openai')
  })

  it('不存在的 id 应返回 undefined', () => {
    const registry = new ModelRegistry(models, 'gpt-4o', 'gpt-4o-mini')
    expect(registry.getModelById('nonexistent')).toBeUndefined()
  })

  it('应该返回默认模型', () => {
    const registry = new ModelRegistry(models, 'gpt-4o', 'gpt-4o-mini')
    expect(registry.getDefaultModel()?.id).toBe('gpt-4o')
  })

  it('应该返回 fallback 模型', () => {
    const registry = new ModelRegistry(models, 'gpt-4o', 'gpt-4o-mini')
    expect(registry.getFallbackModel()?.id).toBe('gpt-4o-mini')
  })

  it('应该按 purpose 过滤模型', () => {
    const registry = new ModelRegistry(models, 'gpt-4o', 'gpt-4o-mini')
    const codingModels = registry.getModelsByPurpose('coding')
    expect(codingModels).toHaveLength(2)
    expect(codingModels.map(m => m.id)).toContain('gpt-4o')
    expect(codingModels.map(m => m.id)).toContain('claude-3-sonnet')
  })

  it('默认模型或 fallback 不存在时应返回 null', () => {
    const registry = new ModelRegistry(models, 'missing-model', 'also-missing')
    expect(registry.getDefaultModel()).toBeNull()
    expect(registry.getFallbackModel()).toBeNull()
  })
})
