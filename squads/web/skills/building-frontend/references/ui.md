# Design rail

The rule of the squad: tokens, not one-off values; hierarchy, not decoration.

## Tokens first

Everything visual comes from custom properties on `:root`:

```css
:root {
  --color-bg: #0e1116; --color-surface: #161b22; --color-text: #e6edf3;
  --color-muted: #9aa4b2; --color-accent: #2f6feb; --color-accent-contrast: #ffffff;
  --font-sans: "Inter Variable", system-ui, sans-serif; --font-display: "Fraunces", serif;
  --step--1: clamp(0.83rem, 0.8rem + 0.2vw, 0.9rem);
  --step-0: clamp(1rem, 0.95rem + 0.3vw, 1.125rem);
  --step-3: clamp(2rem, 1.5rem + 3vw, 3.5rem);
  --space-1: 0.25rem; --space-4: 1rem; --space-8: 2rem; --space-16: 4rem;
  --radius: 12px; --shadow-1: 0 1px 2px rgb(0 0 0 / 0.4), 0 8px 24px rgb(0 0 0 / 0.2);
  --maxw: 72rem;
}
```

Two font families maximum. Fluid sizes with `clamp()`. A component that needs a new value adds a token, never a magic number.

## Hierarchy and layout

- One dominant element per viewport: hero, section title or image. Everything else steps down two levels.
- Type scale with real contrast between steps (1.25 ratio or more). Weights: 400 body, 500-600 labels, 700 display.
- Measure: 45-75 characters per line for prose; `max-width` on the text container, not the page.
- Spacing rhythm from the token scale; sections separated by one `--space-16`-and-up step, not by borders everywhere.
- Layout: a container (`--maxw`) plus an asymmetric grid where the content wants it. Centered everything is the generic default; break it deliberately.
- Breakpoints to verify: 390, 768, 1440. Design mobile first, then let the grid breathe.

## Components

- One job per component, one file per component, variants through props/classes, never a fork of the file.
- Names describe the role (`SiteHeader`, `PriceTable`), not the look.
- A component owns its styles; global CSS holds tokens, resets and base elements only.
- States are part of the component: hover, focus-visible, active, disabled, empty, loading, error.
- Real content in the markup while building; no `lorem ipsum` left at the end.

## Accessibility at build time

- Body text contrast per WCAG 2.2 SC 1.4.3 (4.5:1, large 3:1), UI components per SC 1.4.11 (3:1); check the accent color on both backgrounds.
- `:focus-visible` outline everywhere, never removed; skip link to the main landmark.
- Hit targets at least 24x24 px (WCAG 2.2, 2.5.8), 44 px on touch-first actions.
- Every image has `alt` (empty for decoration); icon-only buttons carry an accessible name.
- Form fields have a visible `label`, an error message tied to the field, and no placeholder-as-label.
- `lang` on `<html>` and on any foreign-language passage; page title describes the page, not the site twice.

## Images and media

- `width`/`height` (or `aspect-ratio`) on every image and embed: no layout shift.
- Lazy-load below-the-fold media; the hero image is eager and preloaded.
- Serve modern formats (`avif`/`webp`) with the stack's image pipeline; never ship an image larger than twice its rendered size.
- Video: `poster`, no autoplay with sound, controls always available.

## Anti-generic checklist

Reject before committing: default framework blue or a violet gradient hero, a centered headline over a stock photo, three feature cards with the same icon set, `#fafafa` page on `#333` text with no palette, rainbow emoji as icons, gratuitous rounded everything, "Lorem" copy, contrast below target, radii and shadows that differ from the tokens.

## Verification

- Screenshots at 390 and 1440 for every page of the milestone; the hierarchy holds at both.
- Contrast, keyboard path and alt text verified, not assumed.
- No hard-coded color, font size or spacing outside the token set.
- The page reads as this brand's, not as a template swap.
