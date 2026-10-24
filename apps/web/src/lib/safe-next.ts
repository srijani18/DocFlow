export const APP_HOME = "/app";

// Any origin works here: it only lets the URL parser resolve and normalise a relative path.
const BASE = new URL("http://docflow.invalid");
// Control characters and whitespace are stripped or rewritten by URL parsers, and
// backslashes are read as slashes, so "/\evil.example" would become "//evil.example".
const SUSPICIOUS = /[\s\\\u0000-\u001f\u007f]/;

/**
 * The page to go to after signing in (spec AC3). Only same-origin paths inside the app
 * are allowed; anything else falls back to the app home, so `?next=` can't be used as an
 * open redirect.
 */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || SUSPICIOUS.test(next)) {
    return APP_HOME;
  }
  let url: URL;
  try {
    url = new URL(next, BASE);
  } catch {
    return APP_HOME;
  }
  // Check the normalised path, so "/app/../admin" can't escape the app.
  const insideApp = url.pathname === APP_HOME || url.pathname.startsWith(`${APP_HOME}/`);
  if (url.origin !== BASE.origin || !insideApp) {
    return APP_HOME;
  }
  return url.pathname + url.search + url.hash;
}

/** The sign-in page, returning to `next` afterwards when it is a safe app path. */
export function loginPath(next: string): string {
  const target = safeNext(next);
  return target === APP_HOME ? "/login" : `/login?next=${encodeURIComponent(target)}`;
}
