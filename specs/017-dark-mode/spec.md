# F17: Dark mode (spec)

**Status:** Implemented (2026-10-28), requested by the owner after Phase 6
**Phase:** 6 (follow-up)
**Plan:** [plan.md](plan.md) · **Tasks:** [tasks.md](tasks.md)

## Summary

DocFlow gets a dark theme for every page (landing, sign-in, the app), in the same indigo-to-violet brand. It follows the device's setting by default, and a **Light / Dark / System** switch lets each person override that on their device.

## User stories

- **US1:** As a user who works in the evening or prefers dark screens, I want DocFlow dark, so that it is comfortable and matches my other apps.
- **US2:** As a user, I want DocFlow to follow my system setting unless I choose otherwise, so that I don't have to set it.

## Acceptance criteria

- **AC1:** With no choice made, DocFlow follows the device's light/dark setting, and switches live when the setting changes.
- **AC2:** A **Light / Dark / System** switch in the app's sidebar (and on the landing and sign-in pages) applies at once and is remembered on this device.
- **AC3:** The page never flashes the wrong theme while loading, including a cold first load.
- **AC4:** Every page is readable in both themes: text, borders, badges, alerts, forms, tables, the metrics chart and the brand gradient. Body text meets WCAG AA contrast (4.5:1) in both.
- **AC5:** The document preview (the PDF itself) stays as the file looks: only DocFlow's own interface changes.

## Non-goals

- Saving the choice to the account (it is per device).
- More themes or custom colours.

## Decisions

- **D1. No library.** A small inline script in `<head>` sets the theme class before the first paint (AC3), and a hook drives the switch. That is about 60 lines, versus `next-themes`, which would be a dependency for the same.
- **D2. Brand-tuned dark tokens.** The dark palette keeps the indigo primary (lighter, for contrast on dark), with slightly indigo-tinted surfaces, instead of the template's grey defaults.
