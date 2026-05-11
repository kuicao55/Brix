#!/usr/bin/env bun
/**
 * Brix CLI 入口 — Phase 3 集成验证版本
 * 验证所有 Phase 3 模块（Router, Orchestrator, Capability）可正确导入和运行
 */
import 'dotenv/config'
import { fileURLToPath } from 'url'
import { loadConfig } from '../config/loader.js'
import { classifyIntent } from '../router/intent.js'
import { evaluate_complexity } from '../router/complexity.js'
import { selectModel } from '../router/model-router.js'
import { StateMachineOrchestrator } from '../orchestrator/state-machine.js'
import { ToolRunner } from '../capability/runner.js'
import { CalculatorTool } from '../capability/tools/calculator.js'
import { WeatherTool } from '../capability/tools/weather.js'
import { FileReadTool } from '../capability/tools/file-read.js'
import { FileWriteTool } from '../capability/tools/file-write.js'
import { FileEditTool } from '../capability/tools/file-edit.js'

/** CLI 主函数 */
export async function main(): Promise<void> {
  console.log('Brix TypeScript Migration - Phase 3 Complete')

  try {
    const config = loadConfig()

    // 测试 Router
    const intent = await classifyIntent('Hello', null as any, config.routing.default_model)
    console.log('Intent:', intent)
    const complexity = evaluate_complexity('Hello')
    console.log('Complexity:', complexity)
    const model = selectModel(intent, complexity, config.routing.default_model, config.routing.fallback_model)
    console.log('Model:', model)

    // 测试 Orchestrator
    const orchestrator = new StateMachineOrchestrator()
    console.log('Orchestrator created')

    // 测试 Capability
    const runner = new ToolRunner()
    runner.register(new CalculatorTool())
    runner.register(new WeatherTool())
    runner.register(new FileReadTool())
    runner.register(new FileWriteTool(config.memory.data_dir))
    runner.register(new FileEditTool(config.memory.data_dir))
    console.log('ToolRunner registered', runner.getToolSchemas().length, 'tools')

    console.log('Phase 3 verification complete!')
  } catch (err) {
    console.error('Failed to load config:', err)
  }
}

// 仅在直接运行时执行，import 时不自动执行（方便测试）
const currentFile = fileURLToPath(import.meta.url)
if (process.argv[1] && currentFile === process.argv[1]) {
  main().catch(console.error)
}
