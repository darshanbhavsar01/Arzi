import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom has no layout engine; Radix only needs a ResizeObserver it can construct and call.
const noop = (): void => undefined;
globalThis.ResizeObserver = class {
  observe = noop;
  unobserve = noop;
  disconnect = noop;
};

afterEach(() => {
  cleanup();
});
