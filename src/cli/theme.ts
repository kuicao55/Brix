import chalk from 'chalk'

/**
 * CLI 主题样式常量
 * 定义 Markdown、工具、加载指示器、阶段等统一配色方案
 */
export const THEME = {
  // Markdown 样式
  markdown: {
    h1: chalk.bold.cyan,
    h2: chalk.bold.white,
    h3: chalk.blue,
    code: chalk.green,
    codeBlock: chalk.bgGray,
    link: chalk.blue.underline,
    em: chalk.italic.magenta,
    strong: chalk.bold.yellow,
    blockquote: chalk.gray,
  },
  // 工具样式
  tool: {
    border: chalk.gray,
    name: chalk.bold.cyan,
    success: chalk.green,
    error: chalk.red,
  },
  // 加载指示器样式
  spinner: {
    active: chalk.blue,
    done: chalk.green,
    failed: chalk.red,
  },
  // 阶段样式
  stage: {
    name: chalk.dim.white,
    time: chalk.dim.cyan,
    detail: chalk.dim.gray,
  },
} as const
