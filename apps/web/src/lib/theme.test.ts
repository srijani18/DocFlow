import {
  chooseTheme,
  readChoice,
  resolveTheme,
  subscribeToTheme,
  THEME_KEY,
  THEME_SCRIPT,
} from "./theme";

function mockSystem(prefersDark: boolean) {
  const listeners = new Set<() => void>();
  const media = {
    matches: prefersDark,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", () => media);
  window.matchMedia = (() => media) as unknown as typeof window.matchMedia;
  return {
    change(dark: boolean) {
      media.matches = dark;
      listeners.forEach((listener) => listener());
    },
  };
}

const root = () => document.documentElement;

beforeEach(() => {
  localStorage.clear();
  root().className = "";
  root().style.colorScheme = "";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("theme", () => {
  it("AC1: system follows the device; an explicit choice wins", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("AC2: a choice is remembered and applied at once", () => {
    mockSystem(false);

    chooseTheme("dark");

    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(root().classList.contains("dark")).toBe(true);
    expect(root().style.colorScheme).toBe("dark");
    expect(readChoice()).toBe("dark");
  });

  it("falls back to system when storage is blocked or holds junk", () => {
    localStorage.setItem(THEME_KEY, "sepia");
    expect(readChoice()).toBe("system");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readChoice()).toBe("system");
  });

  it("AC1: on system, a change of the device's setting applies live", () => {
    const system = mockSystem(false);
    const listener = vi.fn();
    const unsubscribe = subscribeToTheme(listener);

    system.change(true);

    expect(root().classList.contains("dark")).toBe(true);
    expect(listener).toHaveBeenCalled();
    unsubscribe();
  });

  it.each([
    ["dark", false, true],
    ["light", true, false],
    [null, true, true],
    [null, false, false],
  ])(
    "AC3: the inline script applies %s (device dark: %s) before paint",
    (stored, deviceDark, dark) => {
      mockSystem(deviceDark);
      if (stored) localStorage.setItem(THEME_KEY, stored);

      new Function(THEME_SCRIPT)();

      expect(root().classList.contains("dark")).toBe(dark);
      expect(root().style.colorScheme).toBe(dark ? "dark" : "light");
    },
  );
});
