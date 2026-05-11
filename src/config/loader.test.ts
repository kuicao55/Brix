import { describe, it, expect } from 'vitest'
import { deepMerge } from './loader'

describe('deepMerge', () => {
  it('should merge nested objects', () => {
    const target = { a: 1, b: { c: 2 } }
    const source = { b: { d: 3 } }
    const result = deepMerge(target, source)
    expect(result).toEqual({ a: 1, b: { c: 2, d: 3 } })
  })

  it('should skip __proto__ key to prevent prototype pollution', () => {
    const target = { a: 1 }
    const source = JSON.parse('{"__proto__": {"polluted": true}}')
    const result = deepMerge(target, source)
    // 设置 __proto__ 会通过 setter 修改原型链，导致 result.polluted 可访问
    expect((result as any).polluted).toBeUndefined()
    // 其他新对象不应被污染
    expect(({} as any).polluted).toBeUndefined()
  })

  it('should skip constructor key to prevent prototype pollution', () => {
    const target = { a: 1 }
    const source = { constructor: { polluted: true } }
    const result = deepMerge(target, source)
    expect((result as any).constructor).toBe(Object.prototype.constructor)
  })

  it('should skip prototype key to prevent prototype pollution', () => {
    const target = { a: 1 }
    const source = { prototype: { polluted: true } }
    const result = deepMerge(target, source)
    expect((result as any).prototype).toBeUndefined()
  })
})
