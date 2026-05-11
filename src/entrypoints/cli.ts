#!/usr/bin/env bun
/**
 * Brix CLI 入口
 * 启动交互式 REPL 界面
 */
import 'dotenv/config'
import { BrixCLI } from '../cli/app.js'

async function main() {
  const cli = new BrixCLI()
  await cli.run()
}

main().catch(console.error)
