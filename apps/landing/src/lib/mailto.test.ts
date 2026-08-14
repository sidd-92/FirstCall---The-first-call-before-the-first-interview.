import { describe, expect, it, vi } from 'vitest'
import { buildApplicationSubject, getApplicationEmailAddress } from './mailto'

describe('getApplicationEmailAddress', () => {
  it('returns the configured agent email address', () => {
    vi.stubEnv('VITE_AGENT_EMAIL_ADDRESS', 'hiring@example.com')

    expect(getApplicationEmailAddress()).toBe('hiring@example.com')
  })
})

describe('buildApplicationSubject', () => {
  it('builds a plain-text subject tagged with the job id', () => {
    expect(buildApplicationSubject('Senior Baker', '42')).toBe(
      'Application: Senior Baker [JOB-42]',
    )
  })
})
