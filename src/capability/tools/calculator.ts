import { BaseTool } from '../base.js'

/**
 * 计算器工具 — 安全的数学表达式求值
 * 使用递归下降解析器，不使用 eval
 * 支持: +, -, *, /, %, ** (幂), 括号, 一元负号
 * DoS 保护: 表达式长度 <= 1000, 递归深度 <= 100, 指数 <= 1000
 */
export class CalculatorTool extends BaseTool {
  readonly name = 'calculator'
  readonly description = 'Calculate mathematical expressions'
  readonly inputSchema = {
    type: 'object',
    properties: {
      expression: { type: 'string', description: '数学表达式' },
    },
    required: ['expression'],
  }

  async execute(params: Record<string, unknown>): Promise<string> {
    try {
      const expr = params.expression
      if (typeof expr !== 'string') {
        return 'Error: expression 参数必须是字符串'
      }

      const parser = new ExpressionParser(expr)
      const result = parser.parse()
      return String(result)
    } catch (e) {
      const message = e instanceof Error ? e.message : '未知错误'
      return `Error: ${message}`
    }
  }
}

/**
 * 递归下降解析器 — 安全计算数学表达式
 *
 * 语法（优先级从低到高）:
 *   expression = term (('+' | '-') term)*
 *   term       = exponent (('*' | '/' | '%') exponent)*
 *   exponent   = unary ('**' exponent)?  // 右结合
 *   unary      = ('-' unary) | primary
 *   primary    = NUMBER | '(' expression ')'
 */
class ExpressionParser {
  private pos = 0
  private depth = 0
  private readonly expr: string

  constructor(expr: string) {
    this.expr = expr
  }

  parse(): number {
    if (this.expr.length > 1000) {
      throw new Error('表达式长度超过 1000 字符限制（DoS 保护）')
    }

    this.skipWhitespace()
    const result = this.parseExpression()
    this.skipWhitespace()

    if (this.pos < this.expr.length) {
      throw new Error(`意外字符: '${this.expr[this.pos]}'`)
    }

    return result
  }

  /** 解析加减法 */
  private parseExpression(): number {
    let left = this.parseTerm()

    while (this.pos < this.expr.length) {
      this.skipWhitespace()
      const ch = this.expr[this.pos]
      if (ch === '+' || ch === '-') {
        this.pos++
        const right = this.parseTerm()
        left = ch === '+' ? left + right : left - right
      } else {
        break
      }
    }

    return left
  }

  /** 解析乘除模 */
  private parseTerm(): number {
    let left = this.parseExponent()

    while (this.pos < this.expr.length) {
      this.skipWhitespace()
      const ch = this.expr[this.pos]
      if (ch === '*' && this.peek(1) !== '*') {
        // 单独的 * 是乘法，** 是幂运算（在 parseExponent 处理）
        this.pos++
        const right = this.parseExponent()
        left = left * right
      } else if (ch === '/' || ch === '%') {
        this.pos++
        const right = this.parseExponent()
        if (ch === '/') {
          if (right === 0) throw new Error('除以零')
          left = left / right
        } else {
          if (right === 0) throw new Error('除以零')
          left = left % right
        }
      } else {
        break
      }
    }

    return left
  }

  /** 解析幂运算（右结合，DoS 保护: 指数 <= 1000） */
  private parseExponent(): number {
    this.depth++
    if (this.depth > 100) {
      this.depth--
      throw new Error('递归深度超过 100 层限制（DoS 保护）')
    }
    const base = this.parseUnary()

    this.skipWhitespace()
    if (this.pos + 1 < this.expr.length
      && this.expr[this.pos] === '*'
      && this.expr[this.pos + 1] === '*') {
      this.pos += 2
      const exp = this.parseExponent() // 右结合：递归解析

      // DoS 保护：指数必须为整数且 <= 1000
      if (!Number.isInteger(exp)) {
        throw new Error('指数必须是整数')
      }
      if (Math.abs(exp) > 1000) {
        throw new Error('指数不能超过 1000（DoS 保护）')
      }

      this.depth--
      return base ** exp
    }

    this.depth--
    return base
  }

  /** 解析一元负号 */
  private parseUnary(): number {
    this.skipWhitespace()

    if (this.pos < this.expr.length && this.expr[this.pos] === '-') {
      this.depth++
      if (this.depth > 100) {
        this.depth--
        throw new Error('递归深度超过 100 层限制（DoS 保护）')
      }
      this.pos++
      const result = -this.parseUnary()
      this.depth--
      return result
    }

    return this.parsePrimary()
  }

  /** 解析数字或括号表达式 */
  private parsePrimary(): number {
    this.skipWhitespace()

    if (this.pos >= this.expr.length) {
      throw new Error('表达式意外结束')
    }

    // 括号表达式
    if (this.expr[this.pos] === '(') {
      this.depth++
      if (this.depth > 100) {
        this.depth--
        throw new Error('递归深度超过 100 层限制（DoS 保护）')
      }
      try {
        this.pos++
        const result = this.parseExpression()
        this.skipWhitespace()

        if (this.pos >= this.expr.length || this.expr[this.pos] !== ')') {
          throw new Error('缺少右括号')
        }
        this.pos++
        return result
      } finally {
        this.depth--
      }
    }

    // 数字
    return this.parseNumber()
  }

  /** 解析数字（整数和小数） */
  private parseNumber(): number {
    const start = this.pos

    while (this.pos < this.expr.length
      && (this.isDigit(this.expr[this.pos]) || this.expr[this.pos] === '.')) {
      this.pos++
    }

    if (this.pos === start) {
      throw new Error(`期望数字，但遇到 '${this.expr[this.pos]}'`)
    }

    const numStr = this.expr.slice(start, this.pos)

    // 验证数字格式：只允许整数或单个小数点的小数
    if (!/^[0-9]+(\.[0-9]+)?$/.test(numStr)) {
      throw new Error(`无效数字格式: '${numStr}'`)
    }

    const num = Number(numStr)

    if (isNaN(num)) {
      throw new Error(`无效数字: '${numStr}'`)
    }

    return num
  }

  /** 跳过空白字符 */
  private skipWhitespace(): void {
    while (this.pos < this.expr.length && this.expr[this.pos] === ' ') {
      this.pos++
    }
  }

  /** 预览前方字符 */
  private peek(offset: number): string | undefined {
    return this.expr[this.pos + offset]
  }

  /** 判断是否为数字字符 */
  private isDigit(ch: string): boolean {
    return ch >= '0' && ch <= '9'
  }
}
