/**
 * Light / dark theme (F17). The choice is per device, in localStorage; "system" follows the
 * device's setting. `THEME_SCRIPT` applies it before the first paint, so pages never flash.
 */

export type ThemeChoice = "light" | "dark" | "system";
export type Theme = "light" | "dark";

export const THEME_KEY = "docflow-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";
const CHOICES: readonly ThemeChoice[] = ["light", "dark", "system"];

export function readChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    return CHOICES.includes(stored as ThemeChoice) ? (stored as ThemeChoice) : "system";
  } catch {
    return "system"; // storage blocked (private window): follow the device
  }
}

export function systemPrefersDark(): boolean {
  return window.matchMedia(DARK_QUERY).matches;
}

export function resolveTheme(choice: ThemeChoice, prefersDark: boolean): Theme {
  if (choice === "system") return prefersDark ? "dark" : "light";
  return choice;
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

const listeners = new Set<() => void>();

/** Remember the choice on this device and apply it now. */
export function chooseTheme(choice: ThemeChoice): void {
  try {
    window.localStorage.setItem(THEME_KEY, choice);
  } catch {
    // not remembered, but still applied for this page
  }
  applyTheme(resolveTheme(choice, systemPrefersDark()));
  listeners.forEach((listener) => listener());
}

/** For useSyncExternalStore: the choice changes here, in another tab, or (for "system")
 * when the device's setting changes. */
export function subscribeToTheme(listener: () => void): () => void {
  const media = window.matchMedia(DARK_QUERY);
  const onSystemChange = () => {
    if (readChoice() === "system") applyTheme(resolveTheme("system", media.matches));
    listener();
  };
  const onStorage = (event: StorageEvent) => {
    if (event.key !== THEME_KEY) return;
    applyTheme(resolveTheme(readChoice(), media.matches));
    listener();
  };
  listeners.add(listener);
  media.addEventListener("change", onSystemChange);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    media.removeEventListener("change", onSystemChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** Runs in <head> before the page paints: the same rules as above, in plain JavaScript. */
export const THEME_SCRIPT = `(function(){var c="system";try{c=localStorage.getItem("${THEME_KEY}")||"system"}catch(e){}var d=c==="dark"||(c!=="light"&&matchMedia("${DARK_QUERY}").matches);var r=document.documentElement;r.classList.toggle("dark",d);r.style.colorScheme=d?"dark":"light"})()`;
