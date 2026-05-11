/**
 * BrixCLI — 主 REPL 类
 * 整合所有 CLI 组件（Theme, Banner, Spinner, StageIndicator, StreamRenderer,
 * ToolDisplay, Display, Completer, PaginatedSelector）与 Router, Orchestrator,
 * Memory, Capability 层。
 */

import * as readline from 'readline'
import chalk from 'chalk'

import type { BrixConfig } from '../config/loader.js'
import { loadConfig } from '../config/loader.js'
import type { MemoryProvider } from '../memory/types.js'
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
import { renderHistory } from './display.js'
import { COMMANDS } from '../capability/basics/commands.js'
import { classifyIntent } from '../router/intent.js'
import { evaluate_complexity } from '../router/complexity.js'
import { selectModel } from '../router/model-router.js'
import { paginatedSelect } from './paginated-selector.js'
import { getRecentLogs } from '../capability/basics/logs.js'

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
    this.memory = options?.memory ?? null
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
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      completer: (line: string) => completer(line),
    })

    const prompt = () => {
      rl.question(chalk.cyan.bold('  \u276f '), async (input: string) => {
        try {
          const text = input.trim()
          if (!text) {
            prompt()
            return
          }

          // 斜杠命令
          if (text.startsWith('/')) {
            const shouldContinue = await this.handleCommand(text)
            if (shouldContinue) {
              prompt()
              return
            }
            // /quit 返回 false，退出循环
            rl.close()
            return
          }

          // 普通对话 — 流式响应
          console.log()
          try {
            await this.handleChat(text)
          } catch (exc) {
            console.error(chalk.red('Error: ') + (exc instanceof Error ? exc.message : String(exc)))
          }
          prompt()
        } catch (exc) {
          // 捕获 handleCommand 等抛出的异常，防止 unhandled promise rejection
          console.error(chalk.red('Error: ') + (exc instanceof Error ? exc.message : String(exc)))
          prompt()
        }
      })
    }

    // 处理 Ctrl+C / EOF
    rl.on('close', () => {
      console.log('\nGoodbye.')
    })

    prompt()
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
      // 清除会话（如果 memory 存在）
      if (this.memory) {
        try {
          ;(this.memory as any).clearSession?.()
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

      // 有参数时按 ID 恢复
      if (parts.length >= 2) {
        const prefix = parts[1]
        try {
          await this.memory.resumeSession(prefix)
          console.log(`Resumed session ${prefix.slice(0, 8)}...`)
        } catch {
          console.log(`Session not found: ${prefix.slice(0, 8)}...`)
        }
        return true
      }

      // 无参数时使用分页选择器
      const sessions = this.memory.listSessions()
      if (sessions.length === 0) {
        console.log('No sessions available.')
        return true
      }

      const selected = await paginatedSelect(
        sessions,
        (item, idx) => `${item.id.slice(0, 8)}... (${item.message_count} msgs) ${item.preview}`,
        10,
        '选择会话'
      )

      if (selected) {
        try {
          await this.memory.resumeSession(selected.id)
          console.log(`Resumed session ${selected.id.slice(0, 8)}...`)
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
      const logPath = (this.config as any).log_path as string | undefined
      if (logPath) {
        try {
          const logs = getRecentLogs(logPath, 10)
          if (logs.length > 0) {
            for (const entry of logs) {
              const ts = entry.ts ?? '?'
              const trace = entry.trace ?? '?'
              const input = entry.input ?? ''
              const model = entry.model ?? '?'
              const ms = entry.ms_total ?? 0
              const error = entry.error
              const status = error ? 'ERR' : 'OK'
              console.log(`  ${ts}  ${trace}  ${status}  ${model}  ${ms}ms  ${input}`)
            }
          } else {
            console.log('No logs yet.')
          }
        } catch {
          console.log('No logs yet.')
        }
      } else {
        console.log('No logs yet.')
      }
      return true
    }

    if (cmd === '/help') {
      const width = Math.max(...COMMANDS.map(([name]) => name.length)) + 2
      console.log()
      console.log('  Available commands:')
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

    // Memory stage
    indicator.update('Memory')
    const contextMessages: Array<{ role: string; content: string }> = []
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
        // 这里调用 memory 的 add_message 和 save_session
        // 由于 MemoryProvider 接口尚未完全迁移，暂用 try-catch 保护
        ;(this.memory as any).add_message?.('user', userInput)
        if (!response.startsWith('Error')) {
          ;(this.memory as any).add_message?.('assistant', response)
        }
        ;(this.memory as any).save_session?.()
      } catch {
        // fail gracefully
      }
    }

    hooks.fire('persist', { saved: response.startsWith('Error') ? 1 : 2 })

    // Flush log (best-effort)
    try {
      const entry = log.finish()
      // 日志写入暂由 writer.ts 的 writeJsonl 处理
      void entry
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
    this.toolRunner.register(new FileWriteTool())
    this.toolRunner.register(new FileEditTool())
  }

  /** 根据配置构建编排器 */
  private buildOrchestrator(): OrchestratorEngine {
    return new StateMachineOrchestrator()
  }
}
