import chalk from 'chalk'

/**
 * BRIX 启动横幅
 * 显示 ASCII 艺术字、模型、版本、工作目录等信息
 */

const BRIX_ASCII = `
 ██████╗ ██████╗ ██╗██╗  ██╗
 ██╔══██╗██╔══██╗██║╚██╗██╔╝
 ██████╔╝██████╔╝██║ ╚███╔╝
 ██╔══██╗██╔══██║██║ ██╔██╗
 ██████╔╝██║  ██║██║██╔╝ ██╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
`

/**
 * 显示启动横幅
 * @param model - 当前使用的模型名称
 * @param version - Brix 版本号
 * @param cwd - 当前工作目录
 */
export function showBanner(model: string, version: string, cwd: string): void {
  console.log(chalk.bold.cyan(BRIX_ASCII))
  console.log(chalk.dim('  BRIX — Personal AI Agent\n'))
  console.log(chalk.dim('  Model:    ') + chalk.white(model))
  console.log(chalk.dim('  Version:  ') + chalk.white(version))
  console.log(chalk.dim('  Directory: ') + chalk.white(cwd))
  console.log()
  console.log(chalk.dim('  Type /help for commands · Ctrl+C to exit\n'))
}
