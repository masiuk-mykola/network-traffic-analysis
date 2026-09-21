import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Vitest globals are off, so Testing Library cannot register its own cleanup.
afterEach(cleanup)

/**
 * jsdom has neither layout nor a ResizeObserver, so anything that measures an element — Radix's
 * hidden input, the row virtualizer — sees nothing. This reports a fixed viewport once, which is
 * enough for a windowed list to decide what is on screen.
 */
const OBSERVED = { width: 1024, height: 448 }

globalThis.ResizeObserver ??= class {
  private readonly callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }

  observe(target: Element) {
    this.callback(
      [
        { target, contentRect: { ...OBSERVED, top: 0, left: 0, bottom: 0, right: 0, x: 0, y: 0 } },
      ] as never,
      this as never,
    )
  }

  unobserve() {}
  disconnect() {}
}

// The row virtualizer measures with offsetWidth/offsetHeight, which jsdom reports as zero.
Object.defineProperties(HTMLElement.prototype, {
  offsetWidth: { configurable: true, get: () => OBSERVED.width },
  offsetHeight: { configurable: true, get: () => OBSERVED.height },
})

Element.prototype.getBoundingClientRect = function getBoundingClientRect() {
  return {
    width: OBSERVED.width,
    height: OBSERVED.height,
    top: 0,
    left: 0,
    bottom: OBSERVED.height,
    right: OBSERVED.width,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect
}

// jsdom does not scroll, which Radix's select does when it opens.
Element.prototype.scrollIntoView ??= () => undefined

// jsdom has no Pointer Capture; Radix calls it while dismissing a toast.
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.setPointerCapture ??= () => undefined
Element.prototype.releasePointerCapture ??= () => undefined
