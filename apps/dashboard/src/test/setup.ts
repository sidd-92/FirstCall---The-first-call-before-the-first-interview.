import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// vite.config.ts doesn't set test.globals, so @testing-library/react's
// automatic afterEach(cleanup) registration (which relies on a global
// `afterEach`) never fires -- register it explicitly instead, or DOM from
// one test's render() leaks into the next.
afterEach(() => {
  cleanup()
})
