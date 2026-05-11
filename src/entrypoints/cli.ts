#!/usr/bin/env bun
/**
 * Brix CLI 入口 — Phase 1 最小验证版本
 * 后续 milestone 会在此基础上扩展完整 TUI 功能
 */
import 'dotenv/config'
import { fileURLToPath } from 'url'
import { loadConfig } from '../config/loader.js'

/** CLI 主函数 */
export async function main(): Promise<void> {
  console.log('Brix TypeScript Migration - Phase 1 Complete')

  try {
    const config = loadConfig()
    console.log('Config loaded:', config.engine)
  } catch (err) {
    console.error('Failed to load config:', err)
  }
}

// 仅在直接运行时执行，import 时不自动执行（方便测试）
const currentFile = fileURLToPath(import.meta.url)
if (process.argv[1] && currentFile === process.argv[1]) {
  main().catch(console.error)
}
