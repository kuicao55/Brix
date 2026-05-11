import yaml from 'js-yaml'
import fs from 'fs'
import path from 'path'

/** Provider 配置 */
export type ProviderConfig = {
  base_url: string
  api_key_env: string
  protocol: 'openai' | 'anthropic'
}

/** Model 配置 */
export type ModelConfig = {
  id: string
  provider: string
  purpose: string[]
  capabilities: string[]
  max_context: number
  cost_tier: string
  default?: boolean
}

/** Brix 全局配置 */
export type BrixConfig = {
  providers: Record<string, ProviderConfig>
  models: ModelConfig[]
  engine: string
  routing: { default_model: string; fallback_model: string }
  retry: { max_retries: number; base_delay: number; max_delay: number }
  memory: { data_dir: string; max_context_tokens: number }
}

/** 深合并两个对象（source 覆盖 target，递归合并嵌套对象） */
function deepMerge(
  target: Record<string, unknown>,
  source: Record<string, unknown>
): Record<string, unknown> {
  const result = { ...target }
  for (const key of Object.keys(source)) {
    if (
      source[key] &&
      typeof source[key] === 'object' &&
      !Array.isArray(source[key])
    ) {
      result[key] = deepMerge(
        (result[key] || {}) as Record<string, unknown>,
        source[key] as Record<string, unknown>
      )
    } else {
      result[key] = source[key]
    }
  }
  return result
}

/**
 * 加载 Brix 配置
 * @param configDir - 配置目录路径，默认 .brix/
 * @returns 合并后的完整配置
 */
export function loadConfig(configDir?: string): BrixConfig {
  const dir = configDir || path.join(process.cwd(), '.brix')
  const configPath = path.join(dir, 'config.yaml')

  // 默认配置
  const defaultConfig: BrixConfig = {
    providers: {},
    models: [],
    engine: 'state_machine',
    routing: { default_model: 'unknown', fallback_model: 'unknown' },
    retry: { max_retries: 3, base_delay: 1, max_delay: 10 },
    memory: { data_dir: 'src/memory/data', max_context_tokens: 8000 },
  }

  try {
    if (fs.existsSync(configPath)) {
      const content = fs.readFileSync(configPath, 'utf-8')
      const userConfig = yaml.load(content) as Record<string, unknown>
      return deepMerge(defaultConfig, userConfig) as BrixConfig
    }
  } catch (e) {
    console.warn('Failed to load config, using defaults:', e)
  }

  return defaultConfig
}
