# LinkedIn session

The scout never types a password, solves a CAPTCHA or completes a verification. The builder signs in once, in the
shared browser, and every bot run reuses that session.

## The shared browser

- One signed-in headless Chromium on `127.0.0.1:9333`, shared by the bots whose manifest says `shared_browser: true`.
  The scout reaches it through Hermes's `browser_exec` tool, so `new_tab`, `goto_url`, `js` and `page_info` work as
  usual — against that one browser, not a private one.
- A plugin gives each bot run its own tab: the first `new_tab` navigates it, later calls navigate the same tab, and
  the tab is closed when the turn ends. So: one session per card, navigate in place, never open a window, never close
  a tab. A second tab is a second bot's work.
- The browser is signed in because a person signed it in. Nothing in the squad holds the credentials.

## When the session is not signed in

A sign-in page, a checkpoint, a "verify it is you" step or a restriction notice means the session is gone. The scout
does what it can without LinkedIn (portal rows, market keywords from what it already holds), saves that, and ends the
card with:

```
kanban_block(kind="needs_input", reason="LinkedIn needs a sign-in in the shared browser: ask the builder to open the login window")
```

It does not try a saved login, another address, another route into LinkedIn, or a retry later in the same run.

## Notices from LinkedIn

A restriction notice, a "we noticed unusual activity" page or a verification request is a stop sign. LinkedIn work
ends for that card and for the rest of the day: `searches/linkedin-session.json` keeps the counters and the next
card still sees the cap. The card result quotes what the page said. Reading resumes only after the user has looked at
the account and the builder has signed in again.
