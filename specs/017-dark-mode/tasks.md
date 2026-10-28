# F17: Dark mode (tasks)

**Status:** Implemented (2026-10-28)

- [x] **F17-T1: Tokens and theme state** (AC1, AC3): dark tokens, `theme.ts`, the inline script, tests.
- [x] **F17-T2: Switch** (AC2): the segmented control in the sidebar, landing and sign-in, tests.
- [x] **F17-T3: Page audit** (AC4, AC5): every page in both themes, fixes, screenshots in the PR.

## Results (2026-10-28)

- **Browser check (Chromium):**
  - all 8 pages (landing, sign-in, dashboard, documents, document detail, review, metrics, settings) were screenshotted in both themes, with no console errors;
  - the `dark` class is on `<html>` at the first parse of the page (no flash), on a cold load and after a reload with a stored choice;
  - the switch applies at once, is remembered, and "System" follows the device again.
- **Fixed during the audit:**
  - light-only surfaces (`bg-white`) now use theme tokens;
  - the badges on the landing preview and the AI key status pills got dark variants;
  - the inline logo mark got a dark background;
  - the sign-in wordmark chip had light text on a white chip in dark mode;
  - the green trend figure on the landing preview needed a brighter green.
- **Existing bug found and fixed:** the review page scrolled sideways by 347 px in **both** themes. The screen-reader-only "Remove" header in the line-items table is absolutely positioned and escaped its scroll box. The box is now `relative`, and the two-column grid uses `minmax(0, 1fr)`.
