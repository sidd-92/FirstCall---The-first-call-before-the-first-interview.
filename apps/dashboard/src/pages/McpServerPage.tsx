import { useEffect, useRef, useState } from 'react'
import { McpStatusDot } from '@/components/McpStatusDot'
import { McpToolCard } from '@/components/McpToolCard'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuthedApi } from '@/lib/useAuthedApi'
import type { McpStatus, McpTool } from '@/lib/types'

const STATUS_POLL_INTERVAL_MS = 4000

const CHANNEL_BADGE_VARIANT: Record<string, 'secondary' | 'outline' | 'destructive'> = {
  connected: 'secondary',
  connecting: 'outline',
  disconnected: 'outline',
}

export function McpServerPage() {
  const { getMcpServerStatus, listMcpTools, callMcpTool } = useAuthedApi()
  const [status, setStatus] = useState<McpStatus | null>(null)
  const [tools, setTools] = useState<McpTool[] | null>(null)
  const [toolsError, setToolsError] = useState<string | null>(null)

  // Keeps the latest fetcher available to the interval's closure without
  // re-subscribing it on every render (getMcpServerStatus's identity comes
  // from useAuth0's token getter and isn't stable).
  const getStatusRef = useRef(getMcpServerStatus)
  getStatusRef.current = getMcpServerStatus

  useEffect(() => {
    let cancelled = false

    function poll() {
      getStatusRef.current()
        .then((next) => {
          if (!cancelled) setStatus(next)
        })
        .catch(() => {
          if (!cancelled) setStatus({ status: 'disconnected', channels: {} })
        })
    }

    poll()
    const interval = setInterval(poll, STATUS_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    listMcpTools()
      .then(setTools)
      .catch((err: Error) => setToolsError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">MCP Server</h1>
        {status && <McpStatusDot state={status.status} />}
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Connection</CardTitle>
        </CardHeader>
        <CardContent>
          {!status ? (
            <p className="text-sm text-muted-foreground">Checking...</p>
          ) : (
            <div className="flex flex-col gap-3">
              <McpStatusDot state={status.status} />
              {status.status === 'disconnected' && (
                <p className="text-xs text-muted-foreground">
                  No signal from mcp-server right now -- this is expected if it isn&apos;t running.
                </p>
              )}
              {status.status === 'error' && (
                <p className="text-xs text-muted-foreground">
                  mcp-server is reachable but reporting a problem -- check channel status below.
                </p>
              )}
              {Object.keys(status.channels).length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  {Object.entries(status.channels).map(([channel, state]) => (
                    <Badge key={channel} variant={CHANNEL_BADGE_VARIANT[state] ?? 'outline'}>
                      {channel}: {state}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <h2 className="mb-3 text-lg font-semibold tracking-tight">Tools</h2>

      {toolsError && <p className="text-destructive">Failed to load tools: {toolsError}</p>}
      {!toolsError && tools === null && <p className="text-muted-foreground">Loading tools...</p>}
      {tools?.length === 0 && <p className="text-muted-foreground">No tools available.</p>}

      <div className="flex flex-col gap-3">
        {tools?.map((tool) => (
          <McpToolCard key={tool.name} tool={tool} onRun={callMcpTool} />
        ))}
      </div>
    </div>
  )
}
