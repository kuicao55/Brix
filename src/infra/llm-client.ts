import type { Message, LLMResponse, StreamEvent } from '../types.js'
import type { BrixConfig, ProviderConfig } from '../config/loader.js'
import { OpenAICompatProvider } from './providers/openai-compat.js'
import { AnthropicCompatProvider } from './providers/anthropic-compat.js'

/** Provider 联合类型 */
type Provider = OpenAICompatProvider | AnthropicCompatProvider

/**
 * 带指数退避的重试函数
 * @param fn - 要重试的异步函数
 * @param options - 重试配置
 */
async function retry<T>(
  fn: () => Promise<T>,
  options: {
    retries: number
    baseDelay: number
    maxDelay: number
    isRetryable: (e: unknown) => boolean
  }
): Promise<T> {
  for (let attempt = 0; attempt <= options.retries; attempt++) {
    try {
      return await fn()
    } catch (e) {
      if (attempt === options.retries || !options.isRetryable(e)) throw e
      const delay = Math.min(options.baseDelay * Math.pow(2, attempt), options.maxDelay)
      await new Promise(r => setTimeout(r, delay * 1000))
    }
  }
  throw new Error('unreachable')
}

/**
 * 判断错误是否可重试
 * - RateLimit / Timeout / Connection / Internal 错误
 * - 5xx 状态码
 */
function isRetryable(e: unknown): boolean {
  if (e instanceof Error) {
    const name = e.name
    if (
      name.includes('RateLimit') ||
      name.includes('Timeout') ||
      name.includes('Connection') ||
      name.includes('Internal')
    ) {
      return true
    }
    // 检查 status 字段（部分 SDK 会在 Error 上附加 status）
    if ('status' in e && typeof (e as { status: unknown }).status === 'number') {
      const status = (e as { status: number }).status
      return status >= 500 && status < 600
    }
  }
  return false
}

/**
 * LLM 客户端 — 统一接口层
 * 1. 根据模型名路由到正确的 provider
 * 2. 添加带指数退避的重试逻辑
 * 3. 提供 chat() 和 chatStream() 两种调用方式
 */
export class LLMClient {
  private providersConfig: Record<string, ProviderConfig>
  private modelsConfig: import('../config/loader.js').ModelConfig[]
  private providers: Map<string, Provider> = new Map()
  private retryConfig: { max_retries: number; base_delay: number; max_delay: number }
  private routingConfig: { default_model: string; fallback_model: string }

  constructor(config: BrixConfig) {
    this.providersConfig = config.providers
    this.modelsConfig = config.models
    this.retryConfig = config.retry
    this.routingConfig = config.routing
  }

  /**
   * 获取或创建 provider 实例（懒初始化 + 缓存）
   */
  private getProvider(providerName: string): Provider {
    if (!this.providers.has(providerName)) {
      const providerConfig = this.providersConfig[providerName]
      if (!providerConfig) throw new Error(`Unknown provider: ${providerName}`)

      if (providerConfig.protocol === 'openai') {
        this.providers.set(providerName, new OpenAICompatProvider())
      } else if (providerConfig.protocol === 'anthropic') {
        this.providers.set(providerName, new AnthropicCompatProvider())
      } else {
        throw new Error(`Unknown protocol: ${providerConfig.protocol}`)
      }
    }
    return this.providers.get(providerName)!
  }

  /**
   * 非流式 chat 请求（带重试）
   */
  async chat(messages: Message[], model: string, tools?: Record<string, unknown>[]): Promise<LLMResponse> {
    const { providerName, modelName } = this.resolveModel(model)
    const provider = this.getProvider(providerName)
    const providerConfig = this.providersConfig[providerName]

    return retry(
      () => provider.chat({
        messages,
        model: modelName,
        tools,
        baseUrl: providerConfig.base_url,
        apiKey: process.env[providerConfig.api_key_env] || '',
      }),
      {
        retries: this.retryConfig.max_retries,
        baseDelay: this.retryConfig.base_delay,
        maxDelay: this.retryConfig.max_delay,
        isRetryable,
      }
    )
  }

  /**
   * 流式 chat 请求 — 产出 StreamEvent
   */
  async *chatStream(messages: Message[], model: string, tools?: Record<string, unknown>[]): AsyncGenerator<StreamEvent> {
    const { providerName, modelName } = this.resolveModel(model)
    const provider = this.getProvider(providerName)
    const providerConfig = this.providersConfig[providerName]

    yield* provider.chatStream({
      messages,
      model: modelName,
      tools,
      baseUrl: providerConfig.base_url,
      apiKey: process.env[providerConfig.api_key_env] || '',
    })
  }

  /**
   * 解析模型 ID，返回 provider 名称和实际模型名
   * 模型 ID 格式: "provider/model-name" (如 "minimax/MiniMax-M2.7")
   * 实际 API 调用只用 "MiniMax-M2.7"
   */
  private resolveModel(model: string): { providerName: string; modelName: string } {
    // 从 models 配置中查找匹配的模型
    const modelConfig = this.modelsConfig.find(m => m.id === model)
    if (modelConfig) {
      // 从 model ID 中提取实际模型名 (去掉 provider/ 前缀)
      const slashIdx = model.indexOf('/')
      const modelName = slashIdx >= 0 ? model.slice(slashIdx + 1) : model
      return { providerName: modelConfig.provider, modelName }
    }

    // fallback: 尝试按 provider/model 格式解析
    const slashIdx = model.indexOf('/')
    if (slashIdx >= 0) {
      const providerName = model.slice(0, slashIdx)
      const modelName = model.slice(slashIdx + 1)
      if (this.providersConfig[providerName]) {
        return { providerName, modelName }
      }
    }

    // 最后 fallback: 返回第一个 provider
    const names = Object.keys(this.providersConfig)
    if (names.length === 0) {
      throw new Error(`No provider found for model: ${model}`)
    }
    return { providerName: names[0], modelName: model }
  }
}
