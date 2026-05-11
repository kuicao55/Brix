/** Orchestrator 状态枚举 */
export const OrchestratorState = {
  IDLE: 'idle',
  PLANNING: 'planning',
  EXECUTING: 'executing',
  REVIEWING: 'reviewing',
  RESPONDING: 'responding',
} as const

export type OrchestratorState = typeof OrchestratorState[keyof typeof OrchestratorState]
