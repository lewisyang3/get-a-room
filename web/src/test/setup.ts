import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Testing Library only cleans up automatically when test globals are
// enabled, and they aren't here.
afterEach(() => {
  cleanup()
})
