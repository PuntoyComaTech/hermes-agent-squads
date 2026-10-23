# Browser

## Backends and sessions

- `browser.backend` unset means Browser Use mode: the model gets `browser_exec` (Python with helpers `new_tab`,
  `goto_url`, `js`, `page_info`, `cdp`), driven by a `browser_harness` daemon per `session` name.
- Precedence: a cloud provider, Camofox, `browser.cdp_url` (or `BROWSER_CDP_URL`), then `browser.use_real_profile`,
  then the local engine (Hermes's managed Chrome for Testing through agent-browser, or Lightpanda).
- Without a session name every call shares the `default` daemon. With `browser.cdp_url`, a named session is moved to
  a tab it creates; a private browser per name skips that.
- Hermes never stops the harness daemons of a CDP override and never closes their tabs: on a shared browser they
  pile up until something closes them.

## Real profile (`browser.use_real_profile`)

- Snapshots the default Chromium browser's profile (Brave, Chrome, Edge) into
  `<HERMES_HOME>/browser-profile/<browser>` and drives a copy browser on it; `browser.real_profile_pin` names the
  profile directory (`Profile 3`). It restores the owner's open tabs in the copy.
- On macOS and Linux the running browser holds `Login Data` and `Web Data` with a write lock: the snapshot fails
  while any window of that browser is open. Unattended bots therefore cannot rely on it, and squadctl never sets it
  on a bot.

## Signing in for bots

- Google refuses sign-in in a window that has a remote-debugging port or runs headless. The owner signs in in a
  plain visible window (`--user-data-dir=<dir>` and nothing else), quits it, and bots then drive the same directory.
- One Chromium process per profile directory (`SingletonLock`): a second launch on the same directory aborts.
- Exported cookies (`agent-browser state save/load`) work for most sites, but Google ended the session when the same
  cookies ran in several browsers at once.
- `agent-browser --headed` still launched headless here; launch the binary directly for a visible window.
- `AGENT_BROWSER_PROFILE` (profile `.env`) pins agent-browser to a persistent directory; `AGENT_BROWSER_ENCRYPTION_KEY`
  encrypts only named sessions, not `state save` files.

## Squad usage

- `security.website_blocklist` on `browser_exec` matches only URL literals in the code: a redirect, a click or a
  computed URL passes. Contain a signed-in browser at the browser itself (`--host-resolver-rules`).
- `shared_browser: true` in a manifest: `browser.cdp_url` to the machine's shared signed-in browser, the
  `shared-browser-tabs` plugin (records the tabs each call attached; a turn's end closes only those), a 3-hourly
  sweep cron on the manager (two checks 30 s apart). Service and login: `scripts/hpy
  shared_browser.py status|install|login <url>`.
