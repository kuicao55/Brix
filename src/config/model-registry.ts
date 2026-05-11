import type { ModelConfig } from './loader.js'

/** 模型注册表：按 id 索引模型配置，支持默认/fallback 模型和按 purpose 过滤 */
export class ModelRegistry {
  private models: Map<string, ModelConfig> = new Map()
  private defaultModel: ModelConfig | null = null
  private fallbackModel: ModelConfig | null = null

  constructor(models: ModelConfig[], defaultModelId: string, fallbackModelId: string) {
    for (const model of models) {
      this.models.set(model.id, model)
      if (model.id === defaultModelId) this.defaultModel = model
      if (model.id === fallbackModelId) this.fallbackModel = model
    }
  }

  /** 通过 id 查找模型 */
  getModelById(id: string): ModelConfig | undefined {
    return this.models.get(id)
  }

  /** 获取默认模型 */
  getDefaultModel(): ModelConfig | null {
    return this.defaultModel
  }

  /** 获取 fallback 模型 */
  getFallbackModel(): ModelConfig | null {
    return this.fallbackModel
  }

  /** 按 purpose 过滤模型 */
  getModelsByPurpose(purpose: string): ModelConfig[] {
    return [...this.models.values()].filter(m => m.purpose.includes(purpose))
  }
}
