import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { McpStatusDot } from './McpStatusDot'

describe('McpStatusDot', () => {
  it('shows a calm, neutral label for the disconnected state', () => {
    render(<McpStatusDot state="disconnected" />)
    expect(screen.getByText('Disconnected')).toBeInTheDocument()
  })

  it('shows a distinct label for each of the four states', () => {
    const { rerender } = render(<McpStatusDot state="running" />)
    expect(screen.getByText('Connected')).toBeInTheDocument()

    rerender(<McpStatusDot state="starting" />)
    expect(screen.getByText('Starting')).toBeInTheDocument()

    rerender(<McpStatusDot state="error" />)
    expect(screen.getByText('Error')).toBeInTheDocument()

    rerender(<McpStatusDot state="disconnected" />)
    expect(screen.getByText('Disconnected')).toBeInTheDocument()
  })
})
