# F17: Dark mode (plan)

**Status:** Implemented (2026-10-28)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

1. **Tokens** (`globals.css`): rewrite the `.dark` block with brand-tuned values, plus dark versions of the hero glow and the chart colour.
2. **Theme state** (`src/lib/theme.ts`): the choice (`light` | `dark` | `system`) stored in `localStorage` (`docflow-theme`), resolved against `prefers-color-scheme`. Applying it sets `class="dark"` and `color-scheme` on `<html>`. Storage errors (private windows) fall back to `system`.
3. **No flash** (`src/components/theme-script.tsx`): an inline script in the root layout's `<head>` applies the stored choice before paint; `<html suppressHydrationWarning>`.
4. **Switch** (`src/components/theme-switch.tsx`): a three-way segmented control, in the app sidebar footer and the landing and sign-in headers. It listens to system changes while on `system`.
5. **Audit:** screenshot every page in both themes and fix colours that are hard-coded for light (alerts, badges, preview panels).
6. **Tests:** theme resolution and storage fallbacks; the switch updates `<html>` and storage; the script's logic matches the hook's.
