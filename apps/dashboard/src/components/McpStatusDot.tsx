import { cn } from '@/lib/utils'
import type { McpServerState } from '@/lib/types'

const STATE_CONFIG: Record<
  McpServerState,
  { dot: string; pulse: boolean; label: string }
> = {
  running: { dot: 'bg-emerald-500', pulse: true, label: 'Connected' },
  starting: { dot: 'bg-amber-500', pulse: true, label: 'Starting' },
  error: { dot: 'bg-red-500', pulse: false, label: 'Error' },
  disconnected: { dot: 'bg-muted-foreground/40', pulse: false, label: 'Disconnected' },
}

/** Pulse-dot + calm label for the four distinct MCP server states. */
export function McpStatusDot({ state }: { state: McpServerState }) {
  const config = STATE_CONFIG[state]

  return (
    <span className="inline-flex items-center gap-2">
      <span className="relative flex size-2.5">
        {config.pulse && (
          <span
            className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-75', config.dot)}
          />
        )}
        <span className={cn('relative inline-flex size-2.5 rounded-full', config.dot)} />
      </span>
      <span className="text-sm font-medium">{config.label}</span>
    </span>
  )
}
