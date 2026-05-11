import { BaseTool } from '../base.js'

/** 天气数据接口 */
interface WeatherData {
  temp: number
  condition: string
  humidity: number
}

/** 模拟天气数据 */
const WEATHER_DATA: Record<string, WeatherData> = {
  beijing: { temp: 22, condition: 'Sunny', humidity: 45 },
  shanghai: { temp: 25, condition: 'Cloudy', humidity: 70 },
  guangzhou: { temp: 30, condition: 'Rainy', humidity: 85 },
  shenzhen: { temp: 29, condition: 'Partly Cloudy', humidity: 78 },
  hangzhou: { temp: 24, condition: 'Overcast', humidity: 65 },
}

/**
 * 天气工具 — 返回指定城市的模拟天气数据
 * 支持: beijing, shanghai, guangzhou, shenzhen, hangzhou
 */
export class WeatherTool extends BaseTool {
  readonly name = 'weather'
  readonly description = 'Get weather information for a city'
  readonly inputSchema = {
    type: 'object',
    properties: {
      city: { type: 'string' },
    },
    required: ['city'],
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    const city = params.city as string
    const data = WEATHER_DATA[city]

    if (!data) {
      return `Weather data not available for ${city}`
    }

    return `${city}: ${data.temp}°C, ${data.condition}, Humidity: ${data.humidity}%`
  }
}
