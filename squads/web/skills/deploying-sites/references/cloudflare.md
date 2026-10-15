# Provider commands: Cloudflare and Vercel

`cf` covers projects, builds, deploys, versions, DNS, domains, D1, R2 and KV. It is in open beta: confirm every command with `cf cli search "<task>"` before use; the forms below say what to look for.

## Auth

- Token from the profile's passthrough: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
- Named login, when `site.yaml -> provider_profile` is set: `cf auth create <name>`, `cf auth activate <name>`, `cf auth whoami`, `cf auth list`. The precedence between the environment token and a named login is undocumented: run every command as

```bash
env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID cf --profile <name> <command>
```

and confirm the account with `cf auth whoami` before the first deploy.

## Preview and production

- Preview: upload a version from the branch without making it live (`cf workers versions create` or the project's deploy-without-promote form). The preview URL goes in the deploy record.
- Production: record the current `version_id` first (the rollback target), then deploy `main` or promote the uploaded version.
- List versions and deployments before and after, so the record matches reality.
- A Wrangler-configured template (a Next.js or TanStack project scaffolded with Wrangler files) needs `cf migrate --dry-run`, then `cf migrate`, before any `cf dev`, `cf build` or `cf deploy`.
- A Worker's custom domain: declare it in the project config and apply it with `cf workers triggers deploy`; the first (check) run of a `domain` card uses `--dry-run`.

## DNS and domains

- Check run: the zone, its nameservers, and the records that will change.
- Apply run: the site's record, or the nameserver move when the domain is not on Cloudflare yet.

## Data (only when the spec needs it)

- D1: `cf d1 migrations apply` on the deploy stage, never from a build card. Export a backup before a destructive migration with the export command from `cf cli search "d1 export"`.
- R2 and KV: created once at onboarding, bound to the Worker; names recorded in the milestone note, values never.
- A missing token permission: `kanban_block(kind="needs_input", reason="token needs <permission>")`, never a different approach.

## Wrangler exceptions

Only two, and only after `cf cli search` shows there is no `cf` way: setting one secret (`npx wrangler secret put <NAME> --name <worker>`, or a secrets file on a version create) and live logs (`npx wrangler tail <worker>`). Wrangler does not read `cf` named logins: at a site with `provider_profile`, `kanban_block(kind="needs_input", reason="wrangler needs the client's own access")`.

## Vercel sites

Only when `site.yaml -> provider: vercel`. Pass `--token "$VERCEL_TOKEN"` (passthrough) to every command. Preview: `vercel deploy`; production: `vercel promote <preview-url>`; rollback: `vercel rollback <previous-url>`; domain: `vercel domains add <domain>`. A site that earns money never runs on Vercel Hobby: block production until the card names a paid plan.

## Never

- Never edit DNS without the `Confirmed:` line; never delete a zone or record.
- Never deploy a branch other than the reviewed one, and never without the `Confirmed:` line for production.
- Never print the token or paste it into a file, a card or a command that echoes.
