/**
 * Basics 模块测试 — commands, logs, memory-files, sessions
 * TDD: 先写失败测试，再实现
 */

import { describe, expect, it, beforeEach, afterEach } from 'bun:test'
import { writeFileSync, unlinkSync, mkdirSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'

// --- commands 测试 ---

describe('COMMANDS', () => {
  it('应从 basics/commands 导出 COMMANDS 数组', async () => {
    const { COMMANDS } = await import('../src/capability/basics/commands.js')
    expect(Array.isArray(COMMANDS)).toBe(true)
  })

  it('COMMANDS 应包含 9 个命令', async () => {
    const { COMMANDS } = await import('../src/capability/basics/commands.js')
    expect(COMMANDS).toHaveLength(9)
  })

  it('每个 COMMANDS 条目应为 [string, string] 元组', async () => {
    const { COMMANDS } = await import('../src/capability/basics/commands.js')
    for (const entry of COMMANDS) {
      expect(entry).toHaveLength(2)
      expect(typeof entry[0]).toBe('string')
      expect(typeof entry[1]).toBe('string')
    }
  })

  it('COMMANDS 应包含 /help, /quit, /clear, /model, /history, /resume, /soul, /user, /log', async () => {
    const { COMMANDS } = await import('../src/capability/basics/commands.js')
    const names = COMMANDS.map(c => c[0])
    expect(names).toContain('/help')
    expect(names).toContain('/quit')
    expect(names).toContain('/clear')
    expect(names).toContain('/model')
    expect(names).toContain('/history')
    expect(names).toContain('/resume [id]')
    expect(names).toContain('/soul')
    expect(names).toContain('/user')
    expect(names).toContain('/log')
  })
})

// --- logs 测试 ---

describe('logs', () => {
  const testDir = join(tmpdir(), `brix-test-logs-${Date.now()}`)
  const testFile = join(testDir, 'test.jsonl')

  beforeEach(() => {
    mkdirSync(testDir, { recursive: true })
    const entries = [
      JSON.stringify({ trace: 'abc-001', ts: '2025-01-01T10:00:00', input: 'hello', model: 'gpt-4', ms_total: 150 }),
      JSON.stringify({ trace: 'abc-002', ts: '2025-01-01T10:01:00', input: 'world', model: 'claude-3', ms_total: 200 }),
      JSON.stringify({ trace: 'abc-003', ts: '2025-01-01T10:02:00', input: 'test', model: 'gpt-4', ms_total: 100, error: 'timeout' }),
    ]
    writeFileSync(testFile, entries.join('\n') + '\n')
  })

  afterEach(() => {
    try { unlinkSync(testFile) } catch {}
    try { require('fs').rmdirSync(testDir) } catch {}
  })

  describe('getRecentLogs', () => {
    it('应从 basics/logs 导出 getRecentLogs', async () => {
      const { getRecentLogs } = await import('../src/capability/basics/logs.js')
      expect(typeof getRecentLogs).toBe('function')
    })

    it('应返回最近 N 条日志', async () => {
      const { getRecentLogs } = await import('../src/capability/basics/logs.js')
      const logs = getRecentLogs(testFile, 2)
      expect(logs).toHaveLength(2)
      expect(logs[0].trace).toBe('abc-002')
      expect(logs[1].trace).toBe('abc-003')
    })

    it('count 默认为 10', async () => {
      const { getRecentLogs } = await import('../src/capability/basics/logs.js')
      const logs = getRecentLogs(testFile)
      expect(logs).toHaveLength(3) // 只有 3 条，全部返回
    })

    it('文件不存在时应返回空数组', async () => {
      const { getRecentLogs } = await import('../src/capability/basics/logs.js')
      const logs = getRecentLogs('/nonexistent/path.jsonl')
      expect(logs).toEqual([])
    })
  })

  describe('getLogDetail', () => {
    it('应从 basics/logs 导出 getLogDetail', async () => {
      const { getLogDetail } = await import('../src/capability/basics/logs.js')
      expect(typeof getLogDetail).toBe('function')
    })

    it('应返回指定 traceId 的格式化详情', async () => {
      const { getLogDetail } = await import('../src/capability/basics/logs.js')
      const detail = getLogDetail(testFile, 'abc-001')
      expect(detail).not.toBeNull()
      expect(detail!).toContain('abc-001')
      expect(detail!).toContain('hello')
      expect(detail!).toContain('gpt-4')
    })

    it('traceId 不存在时应返回 null', async () => {
      const { getLogDetail } = await import('../src/capability/basics/logs.js')
      const detail = getLogDetail(testFile, 'nonexistent')
      expect(detail).toBeNull()
    })
  })
})

// --- memory-files 测试 ---

describe('memory-files', () => {
  function createMockMemory() {
    return {
      loadSoul: () => '我是 Brix 的灵魂描述',
      loadUserMemory: () => '用户偏好：中文交流',
      listSessions: () => [],
      resumeSession: async () => {},
    }
  }

  describe('loadSoul', () => {
    it('应从 basics/memory-files 导出 loadSoul', async () => {
      const { loadSoul } = await import('../src/capability/basics/memory-files.js')
      expect(typeof loadSoul).toBe('function')
    })

    it('应通过 MemoryProvider 加载 soul 内容', async () => {
      const { loadSoul } = await import('../src/capability/basics/memory-files.js')
      const mock = createMockMemory()
      const result = loadSoul(mock as any)
      expect(result).toBe('我是 Brix 的灵魂描述')
    })
  })

  describe('loadUser', () => {
    it('应从 basics/memory-files 导出 loadUser', async () => {
      const { loadUser } = await import('../src/capability/basics/memory-files.js')
      expect(typeof loadUser).toBe('function')
    })

    it('应通过 MemoryProvider 加载 user 内容', async () => {
      const { loadUser } = await import('../src/capability/basics/memory-files.js')
      const mock = createMockMemory()
      const result = loadUser(mock as any)
      expect(result).toBe('用户偏好：中文交流')
    })
  })
})

// --- sessions 测试 ---

describe('sessions', () => {
  const mockSessions = [
    { id: 'aaa-111', created: '2025-01-01', updated: '2025-01-02', message_count: 5, preview: '你好' },
    { id: 'aaa-222', created: '2025-01-03', updated: '2025-01-04', message_count: 3, preview: '测试' },
    { id: 'bbb-333', created: '2025-01-05', updated: '2025-01-06', message_count: 10, preview: '世界' },
  ]

  function createMockMemory(sessions = mockSessions) {
    return {
      loadSoul: () => '',
      loadUserMemory: () => '',
      listSessions: () => sessions,
      resumeSession: async () => {},
    }
  }

  describe('listSessions', () => {
    it('应从 basics/sessions 导出 listSessions', async () => {
      const { listSessions } = await import('../src/capability/basics/sessions.js')
      expect(typeof listSessions).toBe('function')
    })

    it('应返回所有会话列表', async () => {
      const { listSessions } = await import('../src/capability/basics/sessions.js')
      const mock = createMockMemory()
      const result = listSessions(mock as any)
      expect(result).toHaveLength(3)
      expect(result[0].id).toBe('aaa-111')
    })
  })

  describe('get_session_by_prefix', () => {
    it('应从 basics/sessions 导出 get_session_by_prefix', async () => {
      const { get_session_by_prefix } = await import('../src/capability/basics/sessions.js')
      expect(typeof get_session_by_prefix).toBe('function')
    })

    it('唯一前缀匹配应返回对应会话', async () => {
      const { get_session_by_prefix } = await import('../src/capability/basics/sessions.js')
      const mock = createMockMemory()
      const result = get_session_by_prefix(mock as any, 'bbb')
      expect(result).not.toBeNull()
      expect(result!.id).toBe('bbb-333')
    })

    it('多个匹配时应返回 null', async () => {
      const { get_session_by_prefix } = await import('../src/capability/basics/sessions.js')
      const mock = createMockMemory()
      const result = get_session_by_prefix(mock as any, 'aaa')
      expect(result).toBeNull()
    })

    it('无匹配时应返回 null', async () => {
      const { get_session_by_prefix } = await import('../src/capability/basics/sessions.js')
      const mock = createMockMemory()
      const result = get_session_by_prefix(mock as any, 'zzz')
      expect(result).toBeNull()
    })
  })

  describe('resumeSession', () => {
    it('应从 basics/sessions 导出 resumeSession', async () => {
      const { resumeSession } = await import('../src/capability/basics/sessions.js')
      expect(typeof resumeSession).toBe('function')
    })

    it('有效 sessionId 应返回 true 并调用 memory.resumeSession', async () => {
      const { resumeSession } = await import('../src/capability/basics/sessions.js')
      let called = false
      const mock = {
        ...createMockMemory(),
        resumeSession: async (id: string) => { called = true },
      }
      const result = await resumeSession(mock as any, 'aaa-111')
      expect(result).toBe(true)
      expect(called).toBe(true)
    })

    it('无效 sessionId 应返回 false', async () => {
      const { resumeSession } = await import('../src/capability/basics/sessions.js')
      const mock = createMockMemory()
      const result = await resumeSession(mock as any, 'nonexistent')
      expect(result).toBe(false)
    })
  })
})
