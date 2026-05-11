import * as readline from 'readline'

/**
 * 分页选择器 — 支持键盘导航的交互式列表选择组件
 * 用于会话选择、模型选择等场景
 */
export async function paginatedSelect<T>(
  items: T[],
  formatItem: (item: T, idx: number) => string,
  pageSize: number = 10,
  title: string = 'Select'
): Promise<T | null> {
  if (items.length === 0) return null

  let currentPage = 0
  let selectedIndex = 0
  const totalPages = Math.ceil(items.length / pageSize)

  const render = () => {
    console.clear()
    console.log(`  ${title}\n`)

    const start = currentPage * pageSize
    const pageItems = items.slice(start, start + pageSize)

    for (let i = 0; i < pageItems.length; i++) {
      const globalIdx = start + i + 1
      const label = formatItem(pageItems[i], start + i)
      if (i === selectedIndex) {
        console.log(`  \x1b[36m> ${globalIdx}. ${label}\x1b[0m`)
      } else {
        console.log(`    ${globalIdx}. ${label}`)
      }
    }

    // 补齐空行
    for (let i = pageItems.length; i < pageSize; i++) {
      console.log()
    }

    console.log(`\n  第 ${currentPage + 1}/${totalPages} 页 (共 ${items.length} 项)`)
    console.log('  [↑↓] 上下  [←→] 翻页  [Enter] 确认  [Esc] 取消')
  }

  return new Promise((resolve) => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    })

    // 禁用 echo
    if (process.stdin.isTTY) {
      process.stdin.setRawMode(true)
    }

    render()

    const onKey = (key: Buffer) => {
      const ch = key.toString()

      switch (ch) {
        case '\x1b[A': // 上
          if (selectedIndex > 0) {
            selectedIndex--
          } else if (currentPage > 0) {
            currentPage--
            selectedIndex = Math.min(pageSize - 1, items.length - currentPage * pageSize - 1)
          }
          break
        case '\x1b[B': // 下
          {
            const maxIdx = Math.min(pageSize - 1, items.length - currentPage * pageSize - 1)
            if (selectedIndex < maxIdx) {
              selectedIndex++
            } else if (currentPage < totalPages - 1) {
              currentPage++
              selectedIndex = 0
            }
          }
          break
        case '\x1b[C': // 右
        case '\x1b[5~': // PageUp
          if (currentPage < totalPages - 1) {
            currentPage++
            selectedIndex = Math.min(selectedIndex, items.length - currentPage * pageSize - 1)
          }
          break
        case '\x1b[D': // 左
        case '\x1b[6~': // PageDown
          if (currentPage > 0) {
            currentPage--
            selectedIndex = Math.min(selectedIndex, items.length - currentPage * pageSize - 1)
          }
          break
        case '\r': // Enter
          cleanup()
          resolve(items[currentPage * pageSize + selectedIndex])
          return
        case '\x1b': // Esc
        case 'q':
          cleanup()
          resolve(null)
          return
        case '\x03': // Ctrl+C
          cleanup()
          resolve(null)
          return
        default:
          // 数字键快速跳转
          {
            const num = parseInt(ch)
            if (num >= 1 && num <= 9) {
              const idx = num - 1
              if (idx < items.length - currentPage * pageSize) {
                selectedIndex = idx
              }
            }
          }
          break
      }

      render()
    }

    const cleanup = () => {
      process.stdin.removeListener('data', onKey)
      if (process.stdin.isTTY) {
        process.stdin.setRawMode(false)
      }
      rl.close()
    }

    process.stdin.on('data', onKey)
  })
}
