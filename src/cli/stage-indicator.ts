import { Spinner } from './spinner.js'

const STAGE_LABELS: Record<string, string> = {
  Memory: 'Loading memory...',
  Intent: 'Classifying intent...',
  Complexity: 'Evaluating complexity...',
  Route: 'Selecting model...',
  Planning: 'Planning...',
}

export class StageIndicator {
  private spinner: Spinner
  private finished: boolean = false

  constructor(label: string = 'Thinking...') {
    this.spinner = new Spinner(label)
    this.spinner.start()
  }

  update(stage: string): void {
    if (this.finished) return
    const label = STAGE_LABELS[stage] || 'Working...'
    this.spinner.updateLabel(label)
  }

  finish(): void {
    if (this.finished) return
    this.finished = true
    this.spinner.finish()
  }

  stop_silent(): void {
    if (this.finished) return
    this.finished = true
    this.spinner.stop()
  }

  fail(label: string = 'Error'): void {
    if (this.finished) return
    this.finished = true
    this.spinner.fail(label)
  }
}
