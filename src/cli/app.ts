/**
 * BrixCLI — 主 REPL 类
 * 整合所有 CLI 组件（Theme, Banner, Spinner, StageIndicator, StreamRenderer,
 * ToolDisplay, Display, Completer, PaginatedSelector）与 Router, Orchestrator,
 * Memory, Capability 层。
 */

import * as readline from 'readline'
import * as fs from 'node:fs'
import * as path from 'node:path'
import chalk from 'chalk'

import type { BrixConfig } from '../config/loader.js'
import { loadConfig } from '../config/loader.js'
import type { MemoryProvider } from '../memory/types.js'
import { createMemoryProvider } from '../memory/provider.js'
import type { LLMClient } from '../infra/llm-client.js'
import type { OrchestratorEngine, OrchestratorContext } from '../orchestrator/engine.js'
import type { ToolRunner as ToolRunnerProtocol } from '../orchestrator/engine.js'
import { LLMClient as LLMClientImpl } from '../infra/llm-client.js'
import { ToolRunner } from '../capability/runner.js'
import { StateMachineOrchestrator } from '../orchestrator/state-machine.js'
import { FlowLog } from '../log/flow.js'
import { HookRegistry } from '../hooks/registry.js'
import { CalculatorTool } from '../capability/tools/calculator.js'
import { WeatherTool } from '../capability/tools/weather.js'
import { FileReadTool } from '../capability/tools/file-read.js'
import { FileWriteTool } from '../capability/tools/file-write.js'
import { FileEditTool } from '../capability/tools/file-edit.js'
import { showBanner } from './banner.js'
import { createCompleter } from './completer.js'
import { StageIndicator } from './stage-indicator.js'
import { StreamRenderer } from './stream-renderer.js'
import { ToolDisplay } from './tool-display.js'
import { renderHistory, renderMessage } from './display.js'
import { COMMANDS } from '../capability/basics/commands.js'
import { classifyIntent } from '../router/intent.js'
import { evaluate_complexity } from '../router/complexity.js'
import { selectModel } from '../router/model-router.js'
import { paginatedSelect } from './paginated-selector.js'
import { getRecentLogs, getLogDetail } from '../capability/basics/logs.js'

/** BrixCLI 配置选项 */
export interface BrixCLIOptions {
  /** 自定义 MemoryProvider（用于测试或外部注入） */
  memory?: MemoryProvider
}

/**
 * BrixCLI — 交互式 REPL 界面
 * 将 memory, routing, orchestrator, tools 组合在一起
 */
export class BrixCLI {
  private config: BrixConfig
  private memory: MemoryProvider | null
  private llmClient: LLMClientImpl
  private toolRunner: ToolRunner
  private orchestrator: OrchestratorEngine

  constructor(config?: BrixConfig, options?: BrixCLIOptions) {
    this.config = config ?? loadConfig()
    this.memory = options?.memory ?? createMemoryProvider(this.config.memory.data_dir, this.config.memory.max_context_tokens)
    this.llmClient = new LLMClientImpl(this.config)
    this.toolRunner = new ToolRunner()
    this.registerTools()
    this.orchestrator = this.buildOrchestrator()
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /** 启动 REPL 循环 */
  async run(): Promise<void> {
    const defaultModel = this.config.routing.default_model
    showBanner(defaultModel, '0.1.0', process.cwd())

    const completer = createCompleter()

    // 每轮 prompt 创建新的 readline，避免 paginatedSelect 等操作污染 stdin 状态
    const promptOnce = (): Promise<string | null> =>
      new Promise(resolve => {
        const rl = readline.createInterface({
          input: process.stdin,
          output: process.stdout,
          completer: (line: string) => completer(line),
        })
        let resolved = false
        rl.question(chalk.cyan.bold('  \u276f '), answer => {
          resolved = true
          rl.close()
          resolve(answer)
        })
        // 仅在 Ctrl+D / Ctrl+C 导致的意外关闭时 resolve null
        rl.on('close', () => {
          if (!resolved) resolve(null)
        })
      })

    // eslint-disable-next-line no-constant-condition
    while (true) {
      const input = await promptOnce()
      if (input === null) {
        // Ctrl+D / Ctrl+C
        console.log('\nGoodbye.')
        break
      }

      const text = input.trim()
      if (!text) continue

      // 斜杠命令
      if (text.startsWith('/')) {
        try {
          const shouldContinue = await this.handleCommand(text)
          if (!shouldContinue) break
        } catch (exc) {
          console.error(chalk.red('Error: ') + (exc instanceof Error ? exc.message : String(exc)))
        }
        continue
      }

      // 普通对话 — 流式响应
      // 问→答间距：1 空行（由 console.log 产生）
      console.log()
      try {
        await this.handleChat(text)
      } catch (exc) {
        console.error(chalk.red('Error: ') + (exc instanceof Error ? exc.message : String(exc)))
      }
      // 答→下一问间距：2 空行（轮次间大间距）
      console.log()
      console.log()
    }
  }

  /**
   * 处理斜杠命令
   * 返回 true 表示继续 REPL 循环，false 表示退出
   */
  async handleCommand(text: string): Promise<boolean> {
    const parts = text.trim().split(/\s+/)
    const cmd = parts[0]?.toLowerCase() ?? ''

    // 非斜杠命令不是命令，返回 false 让调用方走 chat 流程
    if (!cmd.startsWith('/')) {
      return false
    }

    if (cmd === '/quit' || cmd === '/exit') {
      return false
    }

    if (cmd === '/clear') {
      if (this.memory) {
        try {
          this.memory.clearSession()
        } catch {
          // fail gracefully
        }
      }
      console.log('Session cleared.')
      return true
    }

    if (cmd === '/model') {
      const defaultModel = this.config.routing.default_model
      console.log(`Current model: ${defaultModel}`)
      return true
    }

    if (cmd === '/history') {
      if (this.memory) {
        try {
          const messages = (this.memory as any).getContextMessages?.('') ?? []
          if (messages.length > 0) {
            renderHistory(messages)
          } else {
            console.log('No history yet.')
          }
        } catch {
          console.log('No history yet.')
        }
      } else {
        console.log('No history yet.')
      }
      return true
    }

    if (cmd === '/resume') {
      if (!this.memory) {
        console.log('No sessions available.')
        return true
      }

      const sessions = this.memory.listSessions()

      // 有参数时按 ID 前缀匹配恢复
      if (parts.length >= 2) {
        const prefix = parts[1]
        const matches = sessions.filter(s => s.id.startsWith(prefix))
        if (matches.length === 1) {
          try {
            await this.memory.resumeSession(matches[0].id)
            this.printResumedMessages(matches[0].id)
          } catch {
            console.log(`Failed to resume session ${prefix.slice(0, 8)}...`)
          }
        } else if (matches.length > 1) {
          console.log(`Ambiguous prefix, ${matches.length} matches. Opening selector...`)
          // 回退到交互式选择器
          const selected = await paginatedSelect(
            matches,
            item => {
              const sid = item.id.slice(0, 8)
              const count = String(item.message_count).padStart(3)
              const date = (item.updated ?? '').slice(0, 10)
              const preview = (item.preview ?? '').slice(0, 40).replace(/\n/g, ' ')
              return `${sid}  ${count} msgs  ${date}  ${preview}`
            },
            10,
            '选择要恢复的会话'
          )
          if (selected) {
            try {
              await this.memory.resumeSession(selected.id)
              this.printResumedMessages(selected.id)
            } catch {
              console.log(`Failed to resume session ${selected.id.slice(0, 8)}...`)
            }
          }
        } else {
          console.log(`Session not found: ${prefix.slice(0, 8)}...`)
        }
        return true
      }

      // 无参数时使用分页选择器
      if (sessions.length === 0) {
        console.log('No sessions yet.')
        return true
      }

      const selected = await paginatedSelect(
        sessions,
        item => {
          const sid = item.id.slice(0, 8)
          const count = String(item.message_count).padStart(3)
          const date = (item.updated ?? '').slice(0, 10)
          const preview = (item.preview ?? '').slice(0, 40).replace(/\n/g, ' ')
          return `${sid}  ${count} msgs  ${date}  ${preview}`
        },
        10,
        '选择要恢复的会话'
      )

      if (selected) {
        try {
          await this.memory.resumeSession(selected.id)
          this.printResumedMessages(selected.id)
        } catch {
          console.log(`Failed to resume session ${selected.id.slice(0, 8)}...`)
        }
      }
      return true
    }

    if (cmd === '/soul') {
      if (this.memory) {
        const content = this.memory.loadSoul()
        if (content) {
          console.log(content)
        } else {
          console.log('No soul.md yet. Start a conversation to create it.')
        }
      } else {
        console.log('No soul.md yet. Start a conversation to create it.')
      }
      return true
    }

    if (cmd === '/user') {
      if (this.memory) {
        const content = this.memory.loadUserMemory()
        if (content) {
          console.log(content)
        } else {
          console.log('No user.md yet. Start a conversation to create it.')
        }
      } else {
        console.log('No user.md yet. Start a conversation to create it.')
      }
      return true
    }

    if (cmd === '/log') {
      const logPath = path.resolve(this.config.memory.data_dir, '..', 'log', 'data', 'brix.jsonl')
      try {
        const logs = getRecentLogs(logPath, 20)
        if (logs.length === 0) {
          console.log('No logs yet.')
          return true
        }

        // 最新在前
        const reversed = [...logs].reverse()

        if (process.stdin.isTTY) {
          // TTY 模式：使用分页选择器（匹配 Python ChoiceInput 行为）
          const selected = await paginatedSelect(
            reversed,
            (item, idx) => {
              const ts = item.ts ?? '?'
              const trace = item.trace ?? '?'
              const ms = item.ms_total ?? 0
              const error = item.error
              const status = error ? 'ERR' : 'OK'
              const preview = String(item.input ?? '').slice(0, 50).replace(/\n/g, ' ')
              return `${ts} [${trace}]  ${ms}ms  ${status}  "${preview}"`
            },
            10,
            '选择日志条目'
          )

          if (selected) {
            const detail = getLogDetail(logPath, String(selected.trace ?? ''))
            if (detail) {
              console.log()
              console.log(detail)
            }
          }
        } else {
          // 非 TTY 模式：显示列表（测试环境）
          console.log()
          for (let i = 0; i < reversed.length; i++) {
            const entry = reversed[i]
            const ts = entry.ts ?? '?'
            const trace = entry.trace ?? '?'
            const ms = entry.ms_total ?? 0
            const error = entry.error
            const status = error ? 'ERR' : 'OK'
            console.log(`  #${i + 1}  ${ts} [${trace}]  ${ms}ms  ${status}`)
          }
        }
      } catch {
        console.log('No logs yet.')
      }
      return true
    }

    if (cmd === '/help') {
      const width = Math.max(...COMMANDS.map(([name]) => name.length)) + 2
      console.log()
      console.log('  可用命令：')
      console.log()
      for (const [name, desc] of COMMANDS) {
        console.log(`    ${name.padEnd(width)} ${desc}`)
      }
      console.log()
      return true
    }

    console.log(`Unknown command: ${cmd}`)
    return true
  }

  /**
   * 处理普通对话输入 — 流式管道
   * Memory -> Intent -> Complexity -> Route -> Orchestrator.runStream()
   */
  async handleChat(userInput: string): Promise<void> {
    const indicator = new StageIndicator()
    const log = new FlowLog(userInput)
    const hooks = new HookRegistry()
    hooks.bindLog(log)

    // Memory stage — 加载 soul + user 作为 system prompt
    indicator.update('Memory')
    const contextMessages: Array<{ role: string; content: string }> = []
    if (this.memory) {
      const parts: string[] = []
      const soul = this.memory.loadSoul()
      if (soul) parts.push(`# Soul\n${soul}`)
      const user = this.memory.loadUserMemory()
      if (user) parts.push(`# User Profile\n${user}`)
      if (parts.length > 0) {
        contextMessages.push({ role: 'system', content: parts.join('\n\n') })
      }
    }
    hooks.fire('memory', { msgs: contextMessages.length })

    // Intent stage
    indicator.update('Intent')
    const defaultModel = this.config.routing.default_model
    let intent: 'chat' | 'task' | 'tool_use' = 'chat'
    try {
      intent = await classifyIntent(userInput, this.llmClient, defaultModel, hooks)
    } catch {
      // 分类失败时回退到 chat
    }

    // Complexity + Route stages
    indicator.update('Complexity')
    const complexity = evaluate_complexity(userInput)
    indicator.update('Route')
    const model = selectModel(intent, complexity, defaultModel, this.config.routing.fallback_model)

    hooks.fire('complexity', { result: complexity })
    hooks.fire('router', { model, reason: `${intent}->${complexity}` })
    log.setModel(model)

    const context: OrchestratorContext = {
      history: contextMessages.map(m => ({ role: m.role as 'user' | 'assistant' | 'system' | 'tool', content: m.content })),
      memory: {},
      toolRunner: this.toolRunner,
      llmClient: this.llmClient,
      model,
      hooks,
    }

    // Planning stage
    indicator.update('Planning')

    let renderer: StreamRenderer | null = null
    const contentParts: string[] = []
    const toolDisplay = new ToolDisplay()

    try {
      for await (const event of this.orchestrator.runStream(userInput, context)) {
        if (event.type === 'text_delta') {
          if (event.text) {
            if (!renderer) {
              toolDisplay.stopThinking()
              indicator.stop_silent()
              renderer = new StreamRenderer()
            }
            renderer.pushDelta(event.text)
            contentParts.push(event.text)
          }
        } else if (event.type === 'tool_call') {
          indicator.finish()
          if (renderer) {
            renderer.flush()
            renderer = null
          }
          console.log()
          toolDisplay.showToolStart(event.name, event.input)
        } else if (event.type === 'tool_result') {
          toolDisplay.showToolResult(event.name, event.result, event.ms, event.is_error)
          console.log()
        }
      }
    } catch (exc) {
      if (renderer) {
        renderer.flush()
        renderer = null
      }
      log.setError(exc instanceof Error ? exc.message : String(exc))
      console.error(chalk.red('Error: ') + (exc instanceof Error ? exc.message : String(exc)))
    } finally {
      toolDisplay.cleanup()
      indicator.finish()
    }

    // Flush remaining content
    if (renderer) {
      renderer.flush()
    }

    const response = contentParts.join('')
    if (response.startsWith('Error')) {
      log.setError(response)
    }

    // Persist conversation (if memory available)
    if (this.memory) {
      try {
        this.memory.addMessage('user', userInput)
        if (!response.startsWith('Error')) {
          this.memory.addMessage('assistant', response)
        }
        this.memory.saveSession()
      } catch {
        // fail gracefully
      }
    }

    hooks.fire('persist', { saved: response.startsWith('Error') ? 1 : 2 })

    // Flush log (best-effort)
    try {
      const entry = log.finish()
      const logDir = path.resolve(this.config.memory.data_dir, '..', 'log', 'data')
      fs.mkdirSync(logDir, { recursive: true })
      const logPath = path.join(logDir, 'brix.jsonl')
      fs.appendFileSync(logPath, JSON.stringify(entry) + '\n')
    } catch {
      // fail gracefully
    }
  }

  // ------------------------------------------------------------------
  // 测试辅助方法 — 暴露内部组件供测试断言
  // ------------------------------------------------------------------

  /** 获取 ToolRunner 实例 */
  getToolRunner(): ToolRunnerProtocol {
    return this.toolRunner
  }

  /** 获取 Orchestrator 实例 */
  getOrchestrator(): OrchestratorEngine {
    return this.orchestrator
  }

  /** 获取 LLMClient 实例 */
  getLLMClient(): LLMClientImpl {
    return this.llmClient
  }

  /** 获取配置 */
  getConfig(): BrixConfig {
    return this.config
  }

  // ------------------------------------------------------------------
  // 内部方法
  // ------------------------------------------------------------------

  /** 注册所有内置工具 */
  private registerTools(): void {
    this.toolRunner.register(new CalculatorTool())
    this.toolRunner.register(new WeatherTool())
    this.toolRunner.register(new FileReadTool())
    this.toolRunner.register(new FileWriteTool(this.config.memory.data_dir))
    this.toolRunner.register(new FileEditTool(this.config.memory.data_dir))
  }

  /** 根据配置构建编排器 */
  private buildOrchestrator(): OrchestratorEngine {
    return new StateMachineOrchestrator()
  }

  /** 恢复会话后渲染历史对话（匹配 Python _print_resumed_messages）
   *  读取 sessions/session-{id}.json 文件并用完整聊天 UI 渲染 */
  private printResumedMessages(sessionId: string): void {
    try {
      const sessionFile = path.join(this.config.memory.data_dir, 'sessions', `session-${sessionId}.json`)
      const raw = fs.readFileSync(sessionFile, 'utf-8')
      const msgs = JSON.parse(raw) as Array<{ role: string; content: string }>
      console.log(chalk.dim(`  Resumed session ${sessionId.slice(0, 8)}... (${msgs.length} messages)`))
      if (msgs.length > 0) {
        console.log()
        renderHistory(msgs)
        console.log()
      }
    } catch {
      console.log(`Session not found: ${sessionId.slice(0, 8)}...`)
    }
  }
}
