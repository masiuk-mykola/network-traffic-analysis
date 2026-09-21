import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest globals are off, so Testing Library cannot register its own cleanup.
afterEach(cleanup)

// jsdom has no ResizeObserver; Radix measures its hidden checkbox input with it.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// jsdom does not scroll, which Radix's select does when it opens.
Element.prototype.scrollIntoView ??= () => undefined

// jsdom has no Pointer Capture; Radix calls it while dismissing a toast.
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.setPointerCapture ??= () => undefined
Element.prototype.releasePointerCapture ??= () => undefined
