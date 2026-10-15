# The five lenses

One subagent per lens, clean context, no writes. Each finding: page, what is wrong, the fix, one line each. Severity `critical` blocks `APPROVED`; everything else is a `note`. Thresholds: `site.yaml -> automation.thresholds`, as applied in `checks.json -> thresholds`.

## Contents

1. Acceptance
2. Visual
3. WCAG 2.2 AA
4. Core Web Vitals
5. Security and SEO

## 1. Acceptance

- Walk each criterion of `spec.md -> Milestones` for this milestone at 390 px and 1440 px: page, action, expected result.
- Forms: submit valid data (arrives), invalid data (error shown, input kept) and empty data.
- Navigation: every menu entry, the 404 path, the language switch keeping the current page, a deep link.
- Content: every page has what the spec promised; drafted copy is still marked; no placeholder text.
- Quote the criterion text in the finding.

## 2. Visual

- Screenshots first: at 390 px the page has one dominant element per viewport and nothing competes with the main action.
- Type steps visibly different; spacing from one scale; measure 45-75 characters; no orphans in headings.
- Mobile: tap targets, no horizontal overflow, sticky elements and the consent strip never cover content or the CTA.
- Against `DESIGN.md`: palette, fonts, tone. Note template patterns: template hero, mixed icon sets, default accent color.

## 3. WCAG 2.2 AA

- `checks.json` axe results (`axe` checks): `critical` or `serious` is critical; `moderate` is a note.
- Keyboard: full path, logical order, visible focus (SC 2.4.7), focus not obscured (SC 2.4.11), no trap (SC 2.1.2), skip link works.
- Contrast: SC 1.4.3 (4.5:1, large text 3:1) and SC 1.4.11 (3:1); check the accent color on every background it appears on.
- Text alternatives (SC 1.1.1): `alt` on meaningful images, empty on decoration, accessible names on icon buttons.
- Structure: `lang` set (SC 3.1.1), headings in order, landmarks, labeled fields (SC 3.3.2), errors tied to fields (SC 3.3.1).
- Target size at least 24x24 px (SC 2.5.8); no drag-only interaction (SC 2.5.7); autoplay over 5 s has a control (SC 2.2.2).
- `prefers-reduced-motion: reduce`: content complete, nothing loops.

## 4. Core Web Vitals

- LCP and CLS: `checks.json -> scores.<page>.lcp_ms` and `.cls` against `core_web_vitals`; the Lighthouse scores against `lighthouse_mobile` (`lighthouse_mobile_ssr` overrides it for `dynamic_seo` and `saas`).
- INP has no lab value in Lighthouse. Record a performance trace with the chrome-devtools MCP while using the main action on mobile emulation, and compare its INP to `core_web_vitals.inp_ms`; `scores.<page>.tbt_ms` over 200 is a note.
- LCP over budget: name the LCP element, whether it is preloaded, and its size and format.
- CLS over budget: images and embeds without dimensions, font swaps, content inserted after load.
- Weight: JS per page, image bytes above the fold, render-blocking CSS and fonts.

## 5. Security and SEO

- Secrets: any `secret-*`, `repo-secrets` or `repo-committed-env` failure in `checks.json` is critical and stops the chain.
- Dependencies: `pnpm -C repo audit --audit-level high` lists none; no unexpected `postinstall`.
- Headers: `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` or CSP `frame-ancestors`, HSTS on https; a CSP or a written reason why not.
- Mixed content: no `http://` asset on an https page; cookies `Secure` and `SameSite=Lax` or `Strict`.
- Forms: no sensitive data in the URL; POST over https; honeypot or rate limit on public forms.
- SEO: unique title and description per page, canonical, sitemap, robots, Open Graph image, structured data where the type fits.
- Privacy: no third-party tracker beyond what the spec and the legal pages declare.
