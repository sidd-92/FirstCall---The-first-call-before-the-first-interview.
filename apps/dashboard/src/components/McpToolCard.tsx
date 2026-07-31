import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { McpTool, McpToolCallResult } from '@/lib/types'

function formatResult(result: McpToolCallResult): string {
  const parsed = result.content.map((block) => {
    try {
      return JSON.parse(block) as unknown
    } catch {
      return block
    }
  })
  const value = parsed.length === 1 ? parsed[0] : parsed
  return JSON.stringify(value, null, 2)
}

function coerceValue(rawValue: string, type: string | undefined): unknown {
  if (type === 'integer') return parseInt(rawValue, 10)
  if (type === 'number') return parseFloat(rawValue)
  if (type === 'boolean') return rawValue === 'true'
  return rawValue
}

interface McpToolCardProps {
  tool: McpTool
  onRun: (toolName: string, args: Record<string, unknown>) => Promise<McpToolCallResult>
}

/** An expandable card for one MCP tool: name, description, a form built
 * dynamically from the tool's JSON schema, a Run button, and the real
 * result (or error) inline once it comes back. */
export function McpToolCard({ tool, onRun }: McpToolCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [values, setValues] = useState<Record<string, string>>({})
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<McpToolCallResult | null>(null)
  const [callError, setCallError] = useState<string | null>(null)

  const properties = tool.input_schema.properties ?? {}
  const propertyEntries = Object.entries(properties)
  const required = new Set(tool.input_schema.required ?? [])

  function updateField(name: string, type: string | undefined) {
    return (event: React.ChangeEvent<HTMLInputElement>) => {
      const raw = type === 'boolean' ? String(event.target.checked) : event.target.value
      setValues((prev) => ({ ...prev, [name]: raw }))
    }
  }

  function buildArguments(): Record<string, unknown> {
    const args: Record<string, unknown> = {}
    for (const [name, schema] of propertyEntries) {
      const raw = values[name]
      if (raw === undefined || raw === '') continue
      args[name] = coerceValue(raw, schema.type)
    }
    return args
  }

  async function handleRun(event: React.FormEvent) {
    event.preventDefault()
    setRunning(true)
    setCallError(null)
    setResult(null)
    try {
      const callResult = await onRun(tool.name, buildArguments())
      setResult(callResult)
    } catch (err) {
      setCallError(err instanceof Error ? err.message : 'Tool call failed.')
    } finally {
      setRunning(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="flex w-full items-center justify-between gap-3 text-left"
          aria-expanded={expanded}
        >
          <div>
            <CardTitle className="font-mono text-sm">{tool.name}</CardTitle>
            {tool.description && <CardDescription>{tool.description}</CardDescription>}
          </div>
          <ChevronDown
            className={cn(
              'size-4 shrink-0 text-muted-foreground transition-transform',
              expanded && 'rotate-180',
            )}
          />
        </button>
      </CardHeader>

      {expanded && (
        <CardContent>
          <form className="flex flex-col gap-3" onSubmit={handleRun}>
            {propertyEntries.length === 0 && (
              <p className="text-xs text-muted-foreground">This tool takes no arguments.</p>
            )}
            {propertyEntries.map(([name, schema]) => {
              const inputId = `${tool.name}-${name}`
              return (
                <div key={name} className="flex flex-col gap-1.5">
                  <Label htmlFor={inputId}>
                    {name}
                    {required.has(name) && <span className="text-destructive"> *</span>}
                    {schema.type && (
                      <span className="ml-1 text-xs text-muted-foreground">({schema.type})</span>
                    )}
                  </Label>
                  {schema.type === 'boolean' ? (
                    <input
                      id={inputId}
                      type="checkbox"
                      className="size-4 rounded border border-input"
                      checked={values[name] === 'true'}
                      onChange={updateField(name, schema.type)}
                    />
                  ) : (
                    <Input
                      id={inputId}
                      type={schema.type === 'integer' || schema.type === 'number' ? 'number' : 'text'}
                      placeholder={schema.description}
                      required={required.has(name)}
                      value={values[name] ?? ''}
                      onChange={updateField(name, schema.type)}
                    />
                  )}
                </div>
              )
            })}
            <Button type="submit" size="sm" disabled={running} className="w-fit">
              {running ? 'Running...' : 'Run'}
            </Button>
          </form>

          {callError && <p className="mt-3 text-sm text-destructive">{callError}</p>}

          {result && (
            <div className="mt-3 rounded-md border bg-muted/30 p-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                {result.is_error ? 'Tool returned an error' : 'Result'}
              </p>
              <pre className="overflow-x-auto text-xs whitespace-pre-wrap">{formatResult(result)}</pre>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}
