/** Router methods recorded by tests that mock `next/navigation`. */
export function createRouterMock() {
  return {
    replace: vi.fn(),
    push: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  };
}
