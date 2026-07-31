import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StageBadge } from './StageBadge'

describe('StageBadge', () => {
  it('renders a human-readable label for each pipeline stage', () => {
    render(<StageBadge stage="screening_assigned" />)
    expect(screen.getByText('Screening Assigned')).toBeInTheDocument()
  })
})
