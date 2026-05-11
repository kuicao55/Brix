import { describe, expect, it, beforeEach, afterEach } from 'bun:test'
import { ModelRegistry } from '../src/config/model-registry.js'
import { loadConfig } from '../src/config/loader.js'
import type { ModelConfig } from '../src/config/loader.js'
import fs from 'fs'
import path from 'path'

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

  it('purpose 字段为 undefined 时不应抛异常', () => {
    const badModel = makeModel({ id: 'bad', purpose: undefined as unknown as string[] })
    const registry = new ModelRegistry([badModel], 'bad', 'bad')
    expect(() => registry.getModelsByPurpose('coding')).not.toThrow()
    expect(registry.getModelsByPurpose('coding')).toHaveLength(0)
  })

  it('重复 model id 时应取最后一个，并从 Map 正确解析 default/fallback', () => {
    const modelsWithDup: ModelConfig[] = [
      makeModel({ id: 'm1', purpose: ['coding'], provider: 'openai' }),
      makeModel({ id: 'm1', purpose: ['chat'], provider: 'anthropic' }),
      makeModel({ id: 'm2', purpose: ['chat'], provider: 'openai' }),
    ]
    const registry = new ModelRegistry(modelsWithDup, 'm1', 'm2')
    // 重复 id 的情况下，Map 只保留最后插入的
    expect(registry.getModelById('m1')?.provider).toBe('anthropic')
    expect(registry.getDefaultModel()?.provider).toBe('anthropic')
    expect(registry.getFallbackModel()?.id).toBe('m2')
  })
})

describe('loadConfig', () => {
  const tmpDir = path.join(__dirname, 'tmp-config')

  beforeEach(() => {
    fs.mkdirSync(tmpDir, { recursive: true })
  })

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true })
  })

  it('应该在没有配置文件时返回默认配置', () => {
    const config = loadConfig(tmpDir)
    expect(config.engine).toBe('state_machine')
    expect(config.retry.max_retries).toBe(3)
    expect(config.memory.max_context_tokens).toBe(8000)
  })

  it('应该加载并深度合并用户配置', () => {
    const configPath = path.join(tmpDir, 'settings.yaml')
    fs.writeFileSync(configPath, `
engine: langgraph
retry:
  max_retries: 5
`)
    const config = loadConfig(tmpDir)
    expect(config.engine).toBe('langgraph')
    expect(config.retry.max_retries).toBe(5)
    expect(config.memory.max_context_tokens).toBe(8000) // 默认值保留
  })
})
