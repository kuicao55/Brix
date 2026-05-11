import { COMMANDS } from '../capability/basics/commands.js'

/**
 * 创建 REPL 斜杠命令补全器
 */
export function createCompleter(): (line: string) => [string[], string] {
  return (line: string): [string[], string] => {
    if (!line.startsWith('/')) {
      return [[], line]
    }

    if (line.includes(' ')) {
      return [[], line]
    }

    const lowerLine = line.toLowerCase()
    const hits = COMMANDS
      .map(([cmd]) => cmd.split(' ')[0]) // "/resume [id]" -> "/resume"
      .filter(cmd => cmd.toLowerCase().startsWith(lowerLine))

    return [hits.length ? hits : COMMANDS.map(([cmd]) => cmd.split(' ')[0]), line]
  }
}
