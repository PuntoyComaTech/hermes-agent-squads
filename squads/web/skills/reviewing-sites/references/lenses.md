# The five lenses

One subagent per lens, clean context, no writes. Each finding: page, what is wrong, how to fix it, one line each. Severity `critical` blocks `APPROVED`; everything else is a `note`.

## Contents

1. Acceptance
2. Visual
3. WCAG 2.2 AA
4. Core Web Vitals
5. Security and SEO

## 1. Acceptance

- Walk each criterion of `spec.md -> Milestones` for this milestone on mobile (390 px) and desktop: page, action, expected result.
- Forms: submit with valid data (arrives where it should), invalid data (clear error, nothing lost), and empty data.
- Navigation: every menu entry, the 404 path, the language switch keeping the current page, a deep link.
- Content: every page has the content the spec promised; drafted copy is still marked; no placeholder text.
- Copy the exact criterion text into the finding so the fixer knows what failed.

## 2. Visual

- Cold look at the screenshots first: does the page read as deliberate at 390 px before any zooming?
- Hierarchy: one dominant element per viewport; type steps visibly different; nothing competing with the main action.
- Spacing: rhythm from one scale; no cramped section next to a generous one by accident.
- Typography: measure 45-75 characters, no orphans in headings, weights consistent.
- Mobile: tap targets, overflow, sticky elements not covering content, cookie/consent strip not blocking the CTA.
- Against `DESIGN.md` when present: palette, fonts, tone. Note generic patterns: template hero, mismatched icon set, default accent color.
- Dark/light or theme variations only when the spec asked for them.

## 3. WCAG 2.2 AA

- axe-core results from `checks.json`: any `critical` or `serious` is critical; `moderate` is a note.
- Keyboard: full path through the page, logical order, visible focus (`:focus-visible`), no trap, skip link works.
- Contrast: 4.5:1 body, 3:1 large and UI components; check the accent color on each background it appears on.
- Text alternatives: `alt` on meaningful images, empty on decoration, accessible names on icon buttons.
- Structure: `lang` set, headings in order, landmarks present, form fields labeled, errors tied to fields.
- Target size 24x24 px minimum (2.5.8), no drag-only interaction, no autoplay over 5 s without a control.
- Reduced motion: with `prefers-reduced-motion: reduce`, content is complete and nothing loops.

## 4. Core Web Vitals

- Compare against `site.yaml -> automation.thresholds` (`lighthouse_mobile`, or `lighthouse_mobile_ssr` for `dynamic_seo` and `saas`) using the numbers in `checks.json`, never a remembered score.
- LCP under 2.5 s: what is the element, is it preloaded, is it an image with the right size and format.
- CLS under 0.1: images and embeds have dimensions; fonts do not shift layout; no banner inserted after load.
- INP under 200 ms: no long task over 50 ms on the critical path; third-party scripts justified.
- Weight: JS budget for the page, image bytes above the fold, render-blocking CSS and fonts.

## 5. Security and SEO hygiene

- Secrets: `check_site.py` scan of loaded bundles and HTML plus the repo and the branch history; any key shape is critical and stops the chain.
- Dependencies: known high or critical vulnerabilities listed; a fresh lockfile; no unexpected postinstall.
- Headers: at least `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` or CSP `frame-ancestors`, HSTS on https; a CSP or a written reason why not.
- Mixed content: no `http://` asset on an https page; cookies set with `secure` and `SameSite=Lax` or `Strict` if any.
- Forms: no sensitive data in the URL; POST over https; honeypot or rate limit on public forms; server-side validation evidenced by the backend lens' checks.
- SEO: title and description unique per page, canonical, sitemap, robots, Open Graph image, structured data where the type fits, headings match the page purpose.
- Privacy: no third-party tracker beyond what the spec and the site's legal pages declare.
