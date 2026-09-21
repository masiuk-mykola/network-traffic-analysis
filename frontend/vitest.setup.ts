import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest globals are off, so Testing Library cannot register its own cleanup.
afterEach(cleanup)

// jsdom has no Pointer Capture; Radix calls it while dismissing a toast.
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.setPointerCapture ??= () => undefined
Element.prototype.releasePointerCapture ??= () => undefined
