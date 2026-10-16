# Provider commands: Cloudflare (and Vercel)

`cf` first: it covers projects, builds, deploys, versions, DNS, domains, D1, R2 and KV. It is in open beta, so
confirm every command instead of recalling one — `cf cli search "<task>"` returns the matches (JSON, first one
best), `cf schema <command>` describes the request it sends, and `--dry-run` prints that request without making
any call. Wrangler is the exception path, not the default.

Launcher, checked once per card: `command -v cf` hits: run `cf ...`; else run every command as `npx cf ...`
(`npx --no-install cf --version` succeeds when a local or cached copy exists; otherwise `npx cf` downloads it on
first use). Same for Wrangler: `wrangler ...` on PATH, else `npx wrangler ...`. The commands below are written
bare; prefix `npx ` when the CLI is not on PATH, and record the form used in `deploy.md`.

## Logins (the user's, once)

- `cf auth login` opens a browser page the user approves. Bots never log in for the user, never type a password.
- `cf auth whoami` is the check before the first command of a card: it names the account and where the credential
  comes from. Not logged in: `kanban_block(kind="capability", reason="cf auth whoami: <its output>")`.
- One login per client folder: `cf auth create <name>` re-authenticates under a name, `cf auth activate
  <name> <site folder>` binds it to that directory, `cf auth list` shows what is bound where. A named login is
  never shared between clients.
- `CLOUDFLARE_API_TOKEN` (with `CLOUDFLARE_ACCOUNT_ID`) is the unattended path only — CI, a headless box — where
  `cf auth login` cannot run. It takes priority over any stored login, so the deployer carries none in its
  environment: a token there would silently shadow the login. Never print one, paste it into a file, a card or a
  command that echoes.
- Missing scope on an interactive command: the CLI says what it wants; `kanban_block(kind="needs_input", reason=
  "cf needs <scope> for the user's account")`. Never a second credential as a workaround.

## Preview and production

- Preview: upload a version from the branch without making it live (`cf cli search "upload a version"` confirms
  the installed CLI's form). The preview URL goes in the deploy record.
- Production: record the current `version_id` first (the rollback target), then deploy `main` or promote the
  uploaded version. Both need the card's `Confirmed:` line.
- List versions and deployments before and after, so the record matches reality.
- A Worker's custom domain: declare it in the project config and apply it with the CLI's trigger form (search
  "custom domain trigger"); a `domain` card's first run passes `--dry-run`.
- Destructive commands (a delete) print `Aborted.` and exit 0 in a non-interactive session: a zero exit is not a
  deletion. `--force` is also an API parameter on some of them; read that command's `--help` before using it.

## A project that ships a Wrangler config

Never run `cf dev`, `cf build` or `cf deploy` in a project that has `wrangler.jsonc`/`wrangler.toml` and no
`cloudflare.config.ts`: they can generate a config that ignores Wrangler, or fail. Two ways out, both fine:

- Keep Wrangler for that project: `wrangler deploy` (or the project's own script) on the same user
  login (`wrangler login`, once). Record it in `deploy.md`.
- Migrate it and use `cf` from then on: `cf migrate --dry-run`, then `cf migrate`, then resolve every
  `TODO(@cloudflare)` comment in the generated `cloudflare.config.ts` — the build fails until they are resolved,
  and a choice the bot cannot make goes to the user.

## The only two Wrangler exceptions

Setting one secret (`wrangler secret put <NAME> --name <worker>`, or a secrets file on a version create) and
live logs (`wrangler tail <worker>`). Both only after `cf cli search` shows no `cf` way. Wrangler does not
read a `cf` named login: at a site with `provider_profile`, `kanban_block(kind="needs_input", reason="wrangler
needs the client's own access")`.

## DNS and domains

- Check run: the zone, its nameservers, and the records that will change.
- Apply run: the site's record, or the nameserver move when the domain is not on Cloudflare yet.

## Data (only when the spec needs it)

- D1: apply migrations on the deploy stage, never from a build card. Search "d1 export" and take a backup before
  a destructive migration.
- R2 and KV: created once at onboarding, bound to the Worker; names recorded in the milestone note, values never.

## Vercel sites — opt-in

Only when `site.yaml -> provider: vercel`; never a default and never suggested. The user runs `vercel login`
once. Commands: preview `vercel deploy`, production `vercel promote <preview-url>`, rollback
`vercel rollback <previous-url>`, domain `vercel domains add <domain>`. No `--token`: the stored login is the
credential. A site that earns money never runs on Vercel Hobby: block production until the card names a paid plan.

## Never

- Never edit DNS without the `Confirmed:` line; never delete a zone or a record.
- Never deploy a branch other than the reviewed one, and never without the `Confirmed:` line for production.
- Never log in as the user (`cf auth login`, `wrangler login`, `vercel login`), and never type a password,
  token or CAPTCHA answer.
- Never print a credential or paste it into a file, a card, a comment or a command that echoes.
