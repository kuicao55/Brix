import { describe, expect, it } from 'bun:test'
import type { Tool } from '../src/capability/base.js'
import { BaseTool } from '../src/capability/base.js'
import { ToolRunner } from '../src/capability/runner.js'
import { CalculatorTool } from '../src/capability/tools/calculator.js'

// --- 测试用具 ---

class EchoTool extends BaseTool {
  readonly name = 'echo'
  readonly description = '回显输入参数'
  readonly inputSchema = {
    type: 'object',
    properties: {
      message: { type: 'string', description: '要回显的消息' },
    },
    required: ['message'],
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    return `echo: ${params.message}`
  }
}

class AddTool extends BaseTool {
  readonly name = 'add'
  readonly description = '两数相加'
  readonly inputSchema = {
    type: 'object',
    properties: {
      a: { type: 'number' },
      b: { type: 'number' },
    },
    required: ['a', 'b'],
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    return String((params.a as number) + (params.b as number))
  }
}

class FailTool extends BaseTool {
  readonly name = 'fail'
  readonly description = '总是失败'
  readonly inputSchema = { type: 'object', properties: {} }

  async execute(_params: Record<string, unknown>): Promise<string> {
    throw new Error('工具执行失败')
  }
}

// --- Tool 接口测试 ---

describe('Tool 接口', () => {
  it('Tool 接口应定义 name, description, inputSchema, execute, toOpenAiSchema', () => {
    // 类型检查：BaseTool 应实现 Tool 的所有成员
    const tool: Tool = new EchoTool()
    expect(tool.name).toBe('echo')
    expect(tool.description).toBe('回显输入参数')
    expect(tool.inputSchema).toBeDefined()
    expect(typeof tool.execute).toBe('function')
    expect(typeof tool.toOpenAiSchema).toBe('function')
  })
})

// --- BaseTool 测试 ---

describe('BaseTool', () => {
  it('toOpenAiSchema() 应返回正确的 OpenAI function calling 格式', () => {
    const tool = new EchoTool()
    const schema = tool.toOpenAiSchema()

    expect(schema).toEqual({
      type: 'function',
      function: {
        name: 'echo',
        description: '回显输入参数',
        parameters: {
          type: 'object',
          properties: {
            message: { type: 'string', description: '要回显的消息' },
          },
          required: ['message'],
        },
      },
    })
  })

  it('execute() 应正确执行并返回结果', async () => {
    const tool = new EchoTool()
    const result = await tool.execute({ message: 'hello' })
    expect(result).toBe('echo: hello')
  })

  it('不同子类的 toOpenAiSchema() 应返回各自的 schema', () => {
    const addTool = new AddTool()
    const schema = addTool.toOpenAiSchema()
    expect((schema.function as any).name).toBe('add')
    expect((schema.function as any).description).toBe('两数相加')
  })
})

// --- ToolRunner 测试 ---

describe('ToolRunner', () => {
  it('register() 注册工具后可通过 run() 执行', async () => {
    const runner = new ToolRunner()
    runner.register(new EchoTool())

    const result = await runner.run('echo', { message: 'test' })
    expect(result).toBe('echo: test')
  })

  it('run() 执行未注册的工具应抛出错误', async () => {
    const runner = new ToolRunner()

    await expect(runner.run('nonexistent', {})).rejects.toThrow('Unknown tool: nonexistent')
  })

  it('register() 多个工具后应能分别执行', async () => {
    const runner = new ToolRunner()
    runner.register(new EchoTool())
    runner.register(new AddTool())

    const echoResult = await runner.run('echo', { message: 'hi' })
    expect(echoResult).toBe('echo: hi')

    const addResult = await runner.run('add', { a: 3, b: 4 })
    expect(addResult).toBe('7')
  })

  it('register() 同名工具应覆盖前一个', async () => {
    const runner = new ToolRunner()
    runner.register(new EchoTool())

    // 注册同名工具
    const overrideTool: Tool = {
      name: 'echo',
      description: '覆盖后的工具',
      inputSchema: {},
      execute: async () => 'overridden',
      toOpenAiSchema: () => ({ type: 'function', function: { name: 'echo' } }),
    }
    runner.register(overrideTool)

    const result = await runner.run('echo', {})
    expect(result).toBe('overridden')
  })

  it('getToolSchemas() 应返回所有已注册工具的 schema', () => {
    const runner = new ToolRunner()
    runner.register(new EchoTool())
    runner.register(new AddTool())

    const schemas = runner.getToolSchemas()
    expect(schemas).toHaveLength(2)

    const names = schemas.map(s => (s.function as any).name)
    expect(names).toContain('echo')
    expect(names).toContain('add')
  })

  it('getToolSchemas() 无注册工具时应返回空数组', () => {
    const runner = new ToolRunner()
    expect(runner.getToolSchemas()).toEqual([])
  })

  it('工具执行失败时 run() 应传播错误', async () => {
    const runner = new ToolRunner()
    runner.register(new FailTool())

    await expect(runner.run('fail', {})).rejects.toThrow('工具执行失败')
  })

  it('ToolRunner 应实现 orchestrator 层的 ToolRunnerProtocol', () => {
    const runner = new ToolRunner()
    // 验证结构兼容性：必须有 run 和 getToolSchemas 方法
    expect(typeof runner.run).toBe('function')
    expect(typeof runner.getToolSchemas).toBe('function')
  })
})

// --- CalculatorTool 测试 ---

describe('CalculatorTool', () => {
  const calc = new CalculatorTool()

  it('应有正确的 name、description 和 inputSchema', () => {
    expect(calc.name).toBe('calculator')
    expect(calc.description).toBe('Calculate mathematical expressions')
    expect(calc.inputSchema).toEqual({
      type: 'object',
      properties: {
        expression: { type: 'string', description: '数学表达式' },
      },
      required: ['expression'],
    })
  })

  it('应返回正确的 OpenAI schema', () => {
    const schema = calc.toOpenAiSchema()
    expect(schema).toEqual({
      type: 'function',
      function: {
        name: 'calculator',
        description: 'Calculate mathematical expressions',
        parameters: {
          type: 'object',
          properties: {
            expression: { type: 'string', description: '数学表达式' },
          },
          required: ['expression'],
        },
      },
    })
  })

  it('应计算基本加法: 2+2 = 4', async () => {
    expect(await calc.execute({ expression: '2+2' })).toBe('4')
  })

  it('应计算基本减法: 5-3 = 2', async () => {
    expect(await calc.execute({ expression: '5-3' })).toBe('2')
  })

  it('应计算基本乘法: 3*4 = 12', async () => {
    expect(await calc.execute({ expression: '3*4' })).toBe('12')
  })

  it('应计算基本除法: 10/2 = 5', async () => {
    expect(await calc.execute({ expression: '10/2' })).toBe('5')
  })

  it('应计算取模: 10%3 = 1', async () => {
    expect(await calc.execute({ expression: '10%3' })).toBe('1')
  })

  it('应计算幂运算: 2**10 = 1024', async () => {
    expect(await calc.execute({ expression: '2**10' })).toBe('1024')
  })

  it('应正确处理运算符优先级: 2+3*4 = 14', async () => {
    expect(await calc.execute({ expression: '2+3*4' })).toBe('14')
  })

  it('应正确处理括号: (2+3)*4 = 20', async () => {
    expect(await calc.execute({ expression: '(2+3)*4' })).toBe('20')
  })

  it('应正确处理一元负号: -5+3 = -2', async () => {
    expect(await calc.execute({ expression: '-5+3' })).toBe('-2')
  })

  it('应处理小数: 3.14*2 = 6.28', async () => {
    expect(await calc.execute({ expression: '3.14*2' })).toBe('6.28')
  })

  it('应处理嵌套括号: ((2+3)*(4-1)) = 15', async () => {
    expect(await calc.execute({ expression: '(2+3)*(4-1)' })).toBe('15')
  })

  it('应处理空格: "2 + 3 * 4" = 14', async () => {
    expect(await calc.execute({ expression: '2 + 3 * 4' })).toBe('14')
  })

  it('应返回除零错误', async () => {
    const result = await calc.execute({ expression: '1/0' })
    expect(result).toMatch(/^Error:/)
  })

  it('应拒绝无效表达式', async () => {
    const result = await calc.execute({ expression: '2++' })
    expect(result).toMatch(/^Error:/)
  })

  it('应拒绝缺少 expression 参数', async () => {
    const result = await calc.execute({})
    expect(result).toMatch(/^Error:/)
  })

  it('应拒绝非字符串 expression', async () => {
    const result = await calc.execute({ expression: 123 })
    expect(result).toMatch(/^Error:/)
  })

  it('DoS 保护: 指数 <= 1000 时正常计算', async () => {
    expect(await calc.execute({ expression: '2**1000' })).toBe(String(2 ** 1000))
  })

  it('DoS 保护: 指数 > 1000 时返回错误', async () => {
    const result = await calc.execute({ expression: '2**1001' })
    expect(result).toMatch(/^Error:/)
  })

  it('应通过 ToolRunner 注册和执行', async () => {
    const runner = new ToolRunner()
    runner.register(calc)

    const result = await runner.run('calculator', { expression: '6*7' })
    expect(result).toBe('42')
  })

  it('DoS 保护: 超长表达式应返回错误', async () => {
    const longExpr = '1' + '+1'.repeat(1000) // 2001 字符
    const result = await calc.execute({ expression: longExpr })
    expect(result).toMatch(/^Error:/)
  })

  it('DoS 保护: 过深嵌套括号应返回错误', async () => {
    const deepExpr = '(' .repeat(200) + '1' + ')'.repeat(200)
    const result = await calc.execute({ expression: deepExpr })
    expect(result).toMatch(/^Error:/)
  })

  it('应拒绝畸形数字字面量 "1.2.3"', async () => {
    const result = await calc.execute({ expression: '1.2.3' })
    expect(result).toMatch(/^Error:/)
  })
})
