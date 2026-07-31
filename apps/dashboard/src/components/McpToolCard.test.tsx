import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { McpToolCard } from './McpToolCard'
import type { McpTool, McpToolCallResult } from '@/lib/types'

const SEND_MESSAGE_TOOL: McpTool = {
  name: 'send_message',
  description: 'Send a new outbound message on an existing conversation.',
  input_schema: {
    type: 'object',
    properties: {
      conversation_id: { type: 'string' },
      text: { type: 'string' },
    },
    required: ['conversation_id', 'text'],
  },
}

const NO_ARGS_TOOL: McpTool = {
  name: 'list_channels',
  description: 'List all channels/connections currently configured.',
  input_schema: { type: 'object', properties: {} },
}

function expandCard(toolName: string) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(toolName) }))
}

describe('McpToolCard', () => {
  it('renders a text input per string schema property, from the real schema (not hardcoded)', () => {
    render(<McpToolCard tool={SEND_MESSAGE_TOOL} onRun={vi.fn()} />)
    expandCard('send_message')

    expect(screen.getByLabelText(/conversation_id/)).toBeInTheDocument()
    expect(screen.getByLabelText(/text/)).toBeInTheDocument()
  })

  it('shows a no-arguments note when the tool schema has no properties', () => {
    render(<McpToolCard tool={NO_ARGS_TOOL} onRun={vi.fn()} />)
    expandCard('list_channels')

    expect(screen.getByText('This tool takes no arguments.')).toBeInTheDocument()
  })

  it('calls onRun with the coerced form values and displays the real result', async () => {
    const result: McpToolCallResult = {
      is_error: false,
      content: [JSON.stringify({ id: 'msg-out-1' })],
      structured_content: null,
    }
    const onRun = vi.fn().mockResolvedValue(result)
    render(<McpToolCard tool={SEND_MESSAGE_TOOL} onRun={onRun} />)
    expandCard('send_message')

    fireEvent.change(screen.getByLabelText(/conversation_id/), {
      target: { value: 'ext-conv-1' },
    })
    fireEvent.change(screen.getByLabelText(/text/), { target: { value: 'hello there' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))

    expect(onRun).toHaveBeenCalledWith('send_message', {
      conversation_id: 'ext-conv-1',
      text: 'hello there',
    })

    expect(await screen.findByText(/msg-out-1/)).toBeInTheDocument()
  })

  it('displays a call error inline without throwing', async () => {
    const onRun = vi.fn().mockRejectedValue(new Error('MCP tool call failed: boom'))
    render(<McpToolCard tool={NO_ARGS_TOOL} onRun={onRun} />)
    expandCard('list_channels')

    fireEvent.click(screen.getByRole('button', { name: 'Run' }))

    expect(await screen.findByText(/MCP tool call failed: boom/)).toBeInTheDocument()
  })
})
