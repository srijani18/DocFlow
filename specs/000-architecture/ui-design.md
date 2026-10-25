# UI design system

**Status:** Adopted (2026-10-26), from a reference landing page the owner supplied.

DocFlow's interface uses one small, consistent visual language. It's implemented with Tailwind tokens in `apps/web/src/app/globals.css` and the shadcn components in `apps/web/src/components/ui/`.

## Tokens

| Token | Value | Use |
|---|---|---|
| Brand gradient | indigo-600 → violet-600 → purple-500 (`--brand-from/via/to`) | Logo mark, headline word ("DocFlow"), one featured card per section, call-to-action bands. Never for body text. |
| Primary | indigo-600 | Main buttons, links, focus rings, active navigation. |
| Surface | very light cool grey (`--surface`) | Page background inside the app and behind landing sections. |
| Cards | white, `rounded-3xl`, 1 px border, small shadow (`Panel`) | Every content block in the app. |
| Shape | Buttons and pills fully rounded; inputs `rounded-xl`; cards `rounded-3xl`; hero panels `rounded-[2.5rem]` | |
| Type | Plus Jakarta Sans (geometric sans); headings `font-semibold tracking-tight` | |

## Patterns

- **Brand-in-headline:** `Why [mark] DocFlow`, with the outlined `InlineMark` and the gradient word (`components/brand.tsx`).
- **Buttons:** `default` (indigo pill), `dark` (black pill, top navigation), `outline` (indigo border), `subtle` (on gradients), `brand` (gradient).
- **Status pills:** soft tinted background per status (queued grey, in-progress indigo/violet with a spinner, needs-review amber, failed red), so status reads at a glance without relying on colour alone (the label is always shown).
- **App shell:** a white sidebar with icon navigation (active item tinted indigo), with content on the grey surface. On phones it becomes a top bar plus a horizontal nav.
- **Landing preview:** a static, clearly illustrative picture of the app (`components/landing/app-preview.tsx`, marked `role="img"`), not live data.

## Rules

- Keep the gradient rare: at most one gradient element per screen section, so it stays a highlight.
- Contrast: body text on white or grey meets WCAG AA. White text appears only on the gradient's darker stops.
- The navigation reads the URL, which is request-time data under Cache Components, so it renders inside `<Suspense>` with an unhighlighted fallback.
