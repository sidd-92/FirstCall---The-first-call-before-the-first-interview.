import { describe, expect, it, vi } from 'vitest'
import { buildApplicationMailto } from './mailto'

describe('buildApplicationMailto', () => {
  it('builds a mailto link with the agent email and a subject tagged with the job id', () => {
    vi.stubEnv('VITE_AGENT_EMAIL_ADDRESS', 'hiring@example.com')

    const link = buildApplicationMailto('Senior Baker', '42')

    expect(link).toBe(
      'mailto:hiring@example.com?subject=Application%3A%20Senior%20Baker%20%5BJOB-42%5D',
    )
  })
})
