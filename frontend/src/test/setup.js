import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

const storedValues = new Map()
const localStorageMock = {
  getItem: (key) => storedValues.get(String(key)) ?? null,
  setItem: (key, value) => storedValues.set(String(key), String(value)),
  removeItem: (key) => storedValues.delete(String(key)),
  clear: () => storedValues.clear(),
  key: (index) => [...storedValues.keys()][index] ?? null,
  get length() { return storedValues.size },
}
Object.defineProperty(window, 'localStorage', { configurable: true, value: localStorageMock })
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: localStorageMock })

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-easy-reading')
  document.documentElement.removeAttribute('data-larger-text')
  document.documentElement.removeAttribute('data-extra-text-spacing')
  document.documentElement.removeAttribute('data-high-contrast')
  document.documentElement.removeAttribute('data-reduced-motion')
  document.documentElement.removeAttribute('data-dyslexia-font')
  document.documentElement.removeAttribute('data-line-focus')
  document.documentElement.removeAttribute('data-accessibility-preset')
})
